ECU_CRITICALITY = {
    "ECU_ENGINE":      5,
    "ECU_BRAKE":       5,
    "ECU_STEERING":    5,
    "ECU_SPEED":       5,
    "ECU_STEER":       5,

    "ECU_ADAS":        4,
    "ECU_BMS":         4,

    "ECU_BODY":        3,

    "ECU_INFOTAINMENT": 1,
}


def get_ecu_weight(ecu_id: str) -> int:
    """Returns criticality weight (1–5). Defaults to 2 for unknown ECUs."""
    return ECU_CRITICALITY.get(ecu_id, 2)
