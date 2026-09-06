import json
import sys
import traceback
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import cast

import httpx

from models import Appointments, Doctor, State
from setup import setup

all_directions = {
    "1": ["Терапевт, Педиатр", "terapevt"],
    "2": ["Стоматология", "stomatolog"],
    "3": ["Гинекология", "ginekolog"],
    "4": ["Другие специальности", "other_doctor"],
}

client: httpx.Client


def get_cookies() -> dict[str, str]:
    p = Path(".data/")

    if not (p / "policy.json").exists():
        setup()

    cookies = json.loads((p / "user.json").read_text(encoding="utf-8"))

    result = {}
    for cookie in cookies:
        name = cookie["name"]
        value = cookie["value"]
        result[name] = value

    return result


def init_session(directions: dict[str, list]) -> State:
    if client is None:
        raise RuntimeError("HTTP-клиент не инициализирован")

    response = client.get("/init")
    globals_id = response.url.params["globalsid"]

    state: State = {
        "policy_params": {
            "globalsid": globals_id,
            "policy_key": None,
        },
        "doctor_params": {
            "globalsid": globals_id,
            "filter": "",
            "attachment": 1,
        },
        "directions": directions,
        "name": "",
        "doctors": [],
        "selected_doctors": [],
        "time": "null",
    }

    return state


def choose_policy(state: State):
    p = Path(".data/policy.json")
    policy = json.loads(p.read_text(encoding="utf-8"))

    policy_dict = {}
    for key in policy:
        num = int(key) + 1
        policy_dict[num] = policy[key]
        print(f"{num} - {policy[key]}")
    print()

    user_choice = get_user_choice("Выберите полис: ", policy_dict)[0]
    policy_key = str(user_choice - 1)
    state["name"] = policy[policy_key]
    state["policy_params"]["policy_key"] = policy_key

    policy_params = tuple(state["policy_params"].items())
    set_policy(policy_params)


@cache
def set_policy(policy_params: tuple):
    params = dict(policy_params)

    client.get("/check-policy-ajax", params=params)


def choose_direction(state: State):
    directions = state["directions"]

    directions_dict = {}
    for i in directions:
        directions_dict[int(i)] = directions[i][0]
        print(f"{i} - {directions[i][0]}")
    print()

    user_choice = get_user_choice("Выберите специальность: ", directions_dict)[0]
    direction = directions[str(user_choice)][1]

    if direction == "stomatolog":
        state["doctor_params"]["attachment"] = 0
    state["doctor_params"]["filter"] = direction

    doctor_params = tuple(state["doctor_params"].items())
    policy_key = state["policy_params"]["policy_key"]
    state["doctors"] = get_doctors(doctor_params, policy_key)


@cache
def get_doctors(doctor_params: tuple, cache_policy_key: str) -> list[Doctor]:
    doctor_params_dict = dict(doctor_params)

    response = client.get("/ajax-source", params=doctor_params_dict)

    return cast(list[Doctor], response.json()["resources"])


def choose_doctors(state: State):
    doctors = [
        doctor["name"] for doctor in state["doctors"] if not doctor["available_dates"]
    ]

    if not doctors:
        raise ValueError("Нет врачей")

    doctors_dict = {}
    for i, doctor in enumerate(doctors, start=1):
        doctors_dict[i] = doctor
        print(f"{i} - {doctor}")
        print(100 * "-")

    user_choices = get_user_choice(
        "Выберите одного или нескольких врачей через пробел: ",
        doctors_dict,
        multiple=True,
    )
    state["selected_doctors"] = []
    for key in user_choices:
        doctor_name = doctors_dict[key]
        state["selected_doctors"].append(doctor_name)


def choose_time(state: State):
    dict_time = {1: "Автозапуск", 2: "Без автозапуска"}
    for key, value in dict_time.items():
        print(f"{key} - {value}")
    print()

    user_choice = get_user_choice("Выберите вариант: ", dict_time)[0]
    if user_choice == 1:
        selected_time = input("Введите время (например 7:00): ").strip()
        state["time"] = selected_time
        set_task(selected_time)
    else:
        state["time"] = "null"


def set_task(selected_time):
    platform = sys.platform

    if platform == "win32":
        from autostart_windows import windows_task

        windows_task(selected_time)
    elif platform == "linux":
        pass


def add_appointment(appointments: Appointments, state: State) -> Appointments:

    time = state["time"]
    name = state["name"]
    policy_params = state["policy_params"]
    doctor_params = state["doctor_params"]
    direction = state["doctor_params"]["filter"]
    doctors = state["selected_doctors"]

    entry = appointments.setdefault(time, {}).setdefault(
        name,
        {
            "policy_params": policy_params,
            "directions": {},
        },
    )

    directions = entry["directions"]
    directions[direction] = {
        "doctor_params": doctor_params,
        "doctors": doctors,
    }

    return deepcopy(appointments)


def finish_record(
    appointments: dict, state: State, current: int
) -> tuple[dict[str, dict], int]:

    appointments = add_appointment(appointments, state)
    current = choose_next_act(current, "Завершить", "Добавить запись")

    start = 0
    finish = 5
    if current == finish:
        p = Path(".data/appointments.json")
        with p.open("w", encoding="utf-8") as f:
            json.dump(appointments, f, ensure_ascii=False, indent=4)
    else:
        current = start

    return appointments, current


def get_user_choice(
    prompt: str,
    options: dict[int, str],
    *,
    multiple: bool = False,
) -> list[int]:
    attempts = 3

    for _ in range(attempts):
        try:
            values = input(prompt).split()
            if not values:
                raise ValueError("Выберите хотя бы один вариант")
            if not multiple and len(values) != 1:
                raise ValueError("Выберите только один вариант")

            choices = [int(value) for value in values]
            if any(choice not in options for choice in choices):
                raise ValueError("Выберите один из доступных вариантов")

            return choices

        except ValueError as e:
            print(f"Ошибка: {e}")

    raise ValueError("Превышены попытки")


def choose_next_act(current: int, first: str = "Дальше", second: str = "Назад") -> int:

    attempts = 3
    for _ in range(attempts):
        try:
            print(f"""
                1 - {first}
                2 - {second}
                """)

            act = int(input("Введите чиcло: ").strip())
            print()

            if act == 1:
                return current + 1
            elif act == 2 and current != 0:
                return current - 1
            elif act == 2:
                return current
            else:
                raise ValueError("Выберите один из доступных вариантов")

        except ValueError as e:
            print(f"Ошибка: {e}")

    raise ValueError("Превышены попытки")


def runner(directions):
    state = init_session(directions)
    appointments: Appointments = {}

    steps = [
        choose_policy,
        choose_direction,
        choose_doctors,
        choose_time,
    ]

    current = 0
    while True:
        steps[current](state)

        current = choose_next_act(current)

        if current == len(steps):
            appointments, current = finish_record(appointments, state, current)
            if current > 0:
                break


def set_config():
    global client
    try:
        client = httpx.Client(
            follow_redirects=True,
            base_url="https://uslugi.tatarstan.ru/mis/tatarstan",
            cookies=get_cookies(),
        )

        runner(all_directions)

    except ValueError as e:
        print(f"Ошибка: {e}")

    except httpx.HTTPError as e:
        print(f"Сетевая ошибка: {e}")

    except Exception:  # noqa: BLE001
        traceback.print_exc()

    finally:
        client.close()


if __name__ == "__main__":
    set_config()
