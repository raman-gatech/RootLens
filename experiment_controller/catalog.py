"""Twenty reproducible Chaos Mesh fault families used by the benchmark."""

from experiment_controller.contracts import ExperimentSpec, FaultType


def scenario(fault_type: FaultType, *, duration_seconds: int = 30) -> ExperimentSpec:
    if fault_type is FaultType.POD_KILL:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            duration_seconds=duration_seconds,
        )
    if fault_type in {FaultType.POD_FAILURE, FaultType.CONTAINER_KILL}:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            duration_seconds=duration_seconds,
            container_names=("checkout",) if fault_type is FaultType.CONTAINER_KILL else (),
        )
    if fault_type is FaultType.CPU_STRESS:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="payment",
            duration_seconds=duration_seconds,
            cpu_workers=1,
            cpu_load_percent=80,
        )
    if fault_type is FaultType.MEMORY_STRESS:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="recommendation",
            duration_seconds=duration_seconds,
            memory_size="128MB",
        )
    if fault_type in {
        FaultType.NETWORK_LATENCY,
        FaultType.NETWORK_DUPLICATE,
        FaultType.NETWORK_CORRUPT,
        FaultType.NETWORK_PARTITION,
    }:
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
    if fault_type is FaultType.BANDWIDTH_LIMIT:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="image-provider",
            duration_seconds=duration_seconds,
            bandwidth_rate="1mbps",
        )
    if fault_type in {
        FaultType.HTTP_DELAY,
        FaultType.HTTP_ABORT,
        FaultType.HTTP_REPLACE,
        FaultType.HTTP_PATCH,
    }:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="frontend-proxy",
            duration_seconds=duration_seconds,
            http_port=8080,
            http_method="GET",
            http_path="*",
            latency_ms=1_000,
        )
    if fault_type in {FaultType.DNS_ERROR, FaultType.DNS_RANDOM}:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="checkout",
            duration_seconds=duration_seconds,
            dns_patterns=("payment.*",),
        )
    if fault_type in {FaultType.IO_LATENCY, FaultType.IO_FAULT}:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="cart",
            duration_seconds=duration_seconds,
            # These are workload paths inside a disposable Chaos Mesh target pod.
            io_volume_path="/tmp",  # nosec B108
            io_path="/tmp/*",  # nosec B108
        )
    if fault_type is FaultType.TIME_SKEW:
        return ExperimentSpec(
            fault_type=fault_type,
            target_service="currency",
            duration_seconds=duration_seconds,
            time_offset="5m",
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
