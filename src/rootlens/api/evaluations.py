"""Publish and retrieve aggregate-only benchmark results."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, status

from rootlens.evaluation import EvaluationReport
from rootlens.evaluation.repository import EvaluationRepository

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


def get_evaluation_repository(request: Request) -> EvaluationRepository:
    return cast(EvaluationRepository, request.app.state.evaluation_repository)


EvaluationRepositoryDependency = Annotated[EvaluationRepository, Depends(get_evaluation_repository)]


@router.get("", response_model=tuple[EvaluationReport, ...])
async def list_evaluations(
    repository: EvaluationRepositoryDependency,
    limit: int = Query(default=20, ge=1, le=100),
) -> tuple[EvaluationReport, ...]:
    return await repository.list(limit=limit)


@router.post("", response_model=EvaluationReport, status_code=status.HTTP_201_CREATED)
async def publish_evaluation(
    report: EvaluationReport, repository: EvaluationRepositoryDependency
) -> EvaluationReport:
    return await repository.save(report)
