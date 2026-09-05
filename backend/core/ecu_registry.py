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


# Human-readable domain for each registered ECU. Purely descriptive: nothing
# in the detection pipeline reads this, it exists so the console can say what
# an ECU *is* rather than only how heavily it is weighted.
#
# Only the ECUs above are listed, which is the honest state of the inventory:
# backend/sim/node_normal.py publishes ECU_001..ECU_120 and none of them are
# registered, so they fall through to DEFAULT_WEIGHT and have no domain. That
# gap is real (an ISO 21434 asset inventory would have to close it) and the
# dashboard reports it as "unclassified" rather than guessing.
ECU_ROLES = {
    "ECU_ENGINE":       "Powertrain — engine control",
    "ECU_BRAKE":        "Chassis — brake actuation",
    "ECU_STEERING":     "Chassis — steering control",
    "ECU_STEER":        "Chassis — steering control",
    "ECU_SPEED":        "Chassis — vehicle speed sensing",
    "ECU_ADAS":         "ADAS — driver assistance",
    "ECU_BMS":          "Powertrain — battery management",
    "ECU_BODY":         "Body — doors, lighting, comfort",
    "ECU_INFOTAINMENT": "Infotainment — head unit",
}

DEFAULT_WEIGHT = 2

CONSISTENCY_ROLE = "Cross-ECU — joint inconsistency across correlated ECUs"


def get_ecu_role(ecu_id: str) -> str | None:
    """Domain string for a registered ECU, or None if it is not in the
    registry. None is a meaningful answer here, not a missing value."""
    if ecu_id.startswith("VEHICLE_CONSISTENCY"):
        return CONSISTENCY_ROLE
    return ECU_ROLES.get(ecu_id)


def describe_ecu(ecu_id: str) -> dict:
    """Everything the registry knows about one id.

    `registered` is False when the weight came from DEFAULT_WEIGHT rather
    than from an entry, which is the difference between "this ECU is low
    criticality" and "nobody has ever classified this ECU".
    """
    synthetic = ecu_id.startswith("VEHICLE_CONSISTENCY")
    return {
        "ecu_id":     ecu_id,
        "role":       get_ecu_role(ecu_id),
        "weight":     get_ecu_weight(ecu_id),
        "registered": synthetic or ecu_id in ECU_CRITICALITY,
        "synthetic":  synthetic,
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
    return ECU_CRITICALITY.get(ecu_id, DEFAULT_WEIGHT)
