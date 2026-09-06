import argparse
import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from random import choice, uniform
from typing import Any, Literal, cast

import httpx

from config import get_cookies
from logger import logger
from models import (
    AppointmentRecords,
    DataInit,
    DataSelect,
    DoctorParams,
    GlobalsParams,
    InitFormData,
    PolicyParams,
)

headers = {
    "x-requested-with": "XMLHttpRequest",
}

ru_directions = {
    "terapevt": "Терапевт, Педиатр",
    "stomatolog": "Стоматология",
    "ginekolog": "Гинекология",
    "other_doctor": "Другие специальности",
}


def get_payload(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        logger.error("Сервер вернул некорректный JSON")
        return False

    if not isinstance(payload, dict):
        logger.error("Ответ сервера должен быть JSON-объектом")
        return False

    return True


async def send_request(
    client: httpx.AsyncClient,
    method: Literal["GET", "POST"],
    url: str,
    params: PolicyParams | DoctorParams | GlobalsParams | None = None,
    data: InitFormData | DataSelect | None = None,
    json: Any | None = None,
    validate_json: bool = False,
) -> httpx.Response:

    attempts = 5

    for _ in range(attempts):
        try:
            response = await client.request(
                method=method,
                url=url,
                params=cast(Any, params),
                data=data,
                json=json,
            )
            response.raise_for_status()
            if validate_json and not get_payload(response):
                await asyncio.sleep(3)
                continue

            return response

        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP ошибка %s при запросе %s\nОжидание 3 секунды",
                e.response.status_code,
                url,
            )
            await asyncio.sleep(3)

        except httpx.TimeoutException:
            logger.warning(
                "Превышено время ожидания при запросе %s",
                url,
            )

        except httpx.HTTPError:
            logger.warning(
                "Сетевая ошибка при запросе %s",
                url,
            )

    raise RuntimeError(f"Не удалось выполнить запрос: {url}")


def create_data_init() -> DataInit:
    return {"select_doctor": {"user": None, "doctor": None}}


def create_globals_params() -> GlobalsParams:
    return {"globalsid": ""}


@dataclass
class UslugiRT:
    whois: str
    client: httpx.AsyncClient
    policy_params: PolicyParams
    doctor_params: DoctorParams
    doctors: list[str]
    data_init: DataInit | None = None
    globals_params: GlobalsParams = field(default_factory=create_globals_params)

    async def get_globals_id(self):
        response = await send_request(
            self.client,
            "GET",
            "/init",
        )

        logger.info(
            "[%s] Инициализация готова",
            self.whois,
        )
        globals_id = response.url.params["globalsid"]

        self.globals_params["globalsid"] = globals_id
        self.doctor_params["globalsid"] = globals_id
        self.policy_params["globalsid"] = globals_id

    async def confirmation_police(self):
        response = await send_request(
            self.client,
            "GET",
            "/check-policy-ajax",
            self.policy_params,
            validate_json=True,
        )

        logger.info(
            "[%s] Полис проверен",
            self.whois,
        )

        self.data_init = {
            "select_doctor": {
                "user": response.json()["user"],
                "doctor": None,
            }
        }

    async def check_dates(self):

        attempts = 75

        for attempt in range(1, attempts + 1):
            response = await send_request(
                self.client,
                "GET",
                "/ajax-source",
                self.doctor_params,
                validate_json=True,
            )

            doctors = response.json()["resources"]

            for selected_doctor in self.doctors:
                for doctor in doctors:
                    if doctor["name"] == selected_doctor and doctor["available_dates"]:
                        if self.data_init is None:
                            raise RuntimeError("Данные инициализации не получены")

                        data_init: DataInit = deepcopy(self.data_init)
                        data_init["select_doctor"]["doctor"] = doctor

                        data_init_form: InitFormData = {
                            "select_doctor": json.dumps(data_init["select_doctor"])
                        }

                        await self.init_data(data_init_form, selected_doctor)
                        break
                else:
                    logger.info(
                        "[%s] попытка %s/%s: Не найдено доступных дат для %s",
                        self.whois,
                        attempt,
                        attempts,
                        selected_doctor,
                    )

            if not self.doctors:
                break

            await asyncio.sleep(uniform(1, 1.5))

    async def init_data(self, data_init: InitFormData, doctor: str):

        await send_request(
            self.client,
            "POST",
            "/init-data-form-source",
            self.globals_params,
            data_init,
        )

        logger.info("[%s] Получены свободные даты для %s", self.whois, doctor)

        await self.choose_ticket(doctor)

    async def choose_ticket(self, doctor: str):
        response = await send_request(
            self.client,
            "GET",
            "/ajax-calendar-data",
            self.globals_params,
            validate_json=True,
        )

        logger.info("[%s] Выбираем случайный слот для %s", self.whois, doctor)

        ticket = choice(response.json()["tickets"])
        appointment_time = choice(ticket)

        day = appointment_time["date"]["day"]
        month = appointment_time["date"]["month"]
        year = appointment_time["date"]["year"]
        select_time, select_id = appointment_time["time"], appointment_time["id"]

        data_select: DataSelect = {
            "selectedDate": f"{day}.{month}.{year} {select_time}",
            "selectedId": select_id,
        }

        await self.confirm_record(data_select, doctor)

    async def confirm_record(self, data_select: DataSelect, doctor: str):

        response = await send_request(
            self.client,
            "POST",
            "/init-record",
            self.globals_params,
            data_select,
            validate_json=True,
        )

        if response.json()["status"] == "success":
            self.doctors.remove(doctor)
            logger.info(
                "[%s] Запись успешно подтверждена для %s\nДата и время: %s",
                self.whois,
                doctor,
                data_select["selectedDate"],
            )

    async def runner(self):
        try:
            await self.get_globals_id()
            await self.confirmation_police()
            await self.check_dates()

        except (
            httpx.HTTPError,
            RuntimeError,
            KeyError,
            TypeError,
            IndexError,
            ValueError,
        ):
            logger.exception("[%s] Произошла ошибка", self.whois)


async def book_appointment(
    client: httpx.AsyncClient,
    appointments: AppointmentRecords,
) -> None:

    coroutines: list[asyncio.Task[None]] = []
    for name, name_data in appointments.items():
        policy_params = name_data["policy_params"]

        for direction, direction_data in name_data["directions"].items():
            doctor_params = direction_data["doctor_params"]
            doctors = direction_data["doctors"]

            ru_direction = ru_directions[direction]
            whois = f"{name} - {ru_direction}"
            patient = UslugiRT(whois, client, policy_params, doctor_params, doctors)
            coroutines.append(asyncio.create_task(patient.runner()))

    await asyncio.wait(coroutines)


async def main(selected_time: str):

    async with httpx.AsyncClient(
        follow_redirects=True,
        base_url="https://uslugi.tatarstan.ru/mis/tatarstan",
        cookies=get_cookies(),
        headers=headers,
    ) as client:
        p = Path(".data/appointments.json")
        all_appointments = json.loads(p.read_text(encoding="utf-8"))

        appointments: AppointmentRecords = {}
        for appointment_time in all_appointments:
            if appointment_time == selected_time:
                appointments.update(all_appointments[selected_time])

        await book_appointment(client, appointments)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--time", default="null")

    logger.info("Запущена новая сессия")

    args = parser.parse_args()
    asyncio.run(main(args.time))
