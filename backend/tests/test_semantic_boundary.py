from app.services.semantic_boundary import SemanticBoundaryService


def test_semantic_boundary_scores_topic_shift_higher() -> None:
    service = SemanticBoundaryService()

    continuous, _ = service.score(
        "The model uses checkpoint recovery and checkpoint state.",
        "Checkpoint state restores the model after a failure.",
    )
    shifted, signals = service.score(
        "The model uses checkpoint recovery.",
        "However, the experiment measures crop disease in field images.",
    )

    assert shifted > continuous
    assert signals["discourseMarker"] is True
    assert "checkpoint" in service.topic("checkpoint checkpoint recovery")
