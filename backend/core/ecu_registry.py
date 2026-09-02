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
    """Returns criticality weight (1–5). Defaults to 2 for unknown ECUs.

    Cross-ECU Consistency Engine findings (backend/core/consistency.py) are
    attributed to a synthetic "VEHICLE_CONSISTENCY::<finding_types>" id
    rather than a single ECU, since they describe a joint inconsistency
    across ECUs, not one ECU's own bad value (Phase3_Plan.md §3.5). They're
    treated as maximum criticality by default: a finding here means
    multiple safety-critical ECUs are already individually passing every
    per-ECU rule while jointly describing something physically impossible.
    """
    if ecu_id.startswith("VEHICLE_CONSISTENCY"):
        return 5
    return ECU_CRITICALITY.get(ecu_id, 2)
