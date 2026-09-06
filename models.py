from typing import Any, TypedDict


class GlobalsParams(TypedDict):
    globalsid: str


class PolicyParams(TypedDict):
    globalsid: str
    policy_key: str | None


class DoctorParams(TypedDict):
    globalsid: str
    filter: str
    attachment: int


class AvailableDates(TypedDict):
    full_date: str
    date: str
    week: str


class Doctor(TypedDict):
    name: str
    available_dates: list[AvailableDates]


class SelectDoctorData(TypedDict):
    user: dict[str, Any] | None
    doctor: Doctor | None


class DataInit(TypedDict):
    select_doctor: SelectDoctorData


class InitFormData(TypedDict):
    select_doctor: str


class DataSelect(TypedDict):
    selectedDate: str
    selectedId: str


class State(TypedDict):
    policy_params: PolicyParams
    doctor_params: DoctorParams
    directions: dict[str, list[str]]
    name: str
    doctors: list[Doctor]
    selected_doctors: list[str]
    time: str


class AppointmentDirection(TypedDict):
    doctor_params: DoctorParams
    doctors: list[str]


class Appointment(TypedDict):
    policy_params: PolicyParams
    directions: dict[str, AppointmentDirection]


type AppointmentRecords = dict[str, Appointment]
type Appointments = dict[str, AppointmentRecords]
