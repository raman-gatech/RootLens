"""Five reproducible initial fault scenarios required by Milestone 4."""

from experiment_controller.contracts import ExperimentSpec, FaultType


def scenario(fault_type: FaultType, *, duration_seconds: int = 30) -> ExperimentSpec:
    if fault_type is FaultType.POD_KILL:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            duration_seconds=duration_seconds,
        )
    if fault_type is FaultType.CPU_STRESS:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="payment",
            duration_seconds=duration_seconds,
            cpu_workers=1,
            cpu_load_percent=80,
        )
    if fault_type is FaultType.NETWORK_LATENCY:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            target_dependency="payment",
            duration_seconds=duration_seconds,
            latency_ms=1_500,
            jitter_ms=100,
        )
    if fault_type is FaultType.PACKET_LOSS:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            target_dependency="payment",
            duration_seconds=duration_seconds,
            packet_loss_percent=30,
        )
    return ExperimentSpec(
        fault_type=fault_type,
        target_service="frontend-proxy",
        duration_seconds=duration_seconds,
        http_port=8080,
        http_method="GET",
        http_path="*",
        latency_ms=1_000,
    )


def catalog() -> tuple[ExperimentSpec, ...]:
    return tuple(scenario(fault_type) for fault_type in FaultType)
