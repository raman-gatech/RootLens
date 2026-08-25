"""Dataset cardinality, ground-truth isolation, and benchmark metric tests."""

from evaluation_harness.dataset import build_dataset
from evaluation_harness.runner import run_benchmark


def test_dataset_contains_five_repetitions_of_twenty_fault_types() -> None:
    dataset = build_dataset(repetitions=5)

    assert len(dataset) == 100
    assert len({item.fault_type for item in dataset}) == 20
    assert all(
        sum(item.fault_type == fault for item in dataset) == 5
        for fault in {item.fault_type for item in dataset}
    )


def test_aggregate_report_contains_baselines_and_ablations_without_ground_truth() -> None:
    report = run_benchmark(repetitions=5)
    serialized = report.model_dump_json()

    assert report.incident_count == 100
    assert set(report.methods) == {
        "A_alert_only",
        "B_single_agent_proxy",
        "C_retrieval_agent_proxy",
        "D_multi_agent",
        "E_rootlens",
    }
    assert len(report.ablations) == 7
    assert "root_cause_service" not in serialized
    assert "ground_truth" not in serialized
    assert report.methods["E_rootlens"].hallucinated_evidence_rate == 0
    assert report.methods["E_rootlens"].evidence_precision == 1
