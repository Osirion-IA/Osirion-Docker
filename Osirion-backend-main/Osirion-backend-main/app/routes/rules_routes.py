# app/routes/rules_routes.py
"""CRUD du moteur de règles (décision). Lecture VIEWER+, écriture USER/ADMIN.
Les règles sont évaluées à l'ingestion d'événement (services/rule_engine)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from app.database import get_session
from app.models.rules import Rule
from app.models.work_schedule import WorkSchedule
from app.models.users import User
from app.schemas.rules_schema import RuleCreate, RuleUpdate, RuleRead
from app.middleware.auth_middleware import require_viewer, require_user

router = APIRouter()

GROUP_SCOPED_TRIGGERS = {"POST_VACANT", "STAFFING_LOW"}


def _validate_group_scope(
    session: Session, trigger: str, work_schedule_id: int | None
) -> None:
    if work_schedule_id is None:
        return
    if trigger not in GROUP_SCOPED_TRIGGERS:
        raise HTTPException(
            status_code=400,
            detail="La portée par groupe est disponible pour les postes vacants et le sous-effectif.",
        )
    if not session.get(WorkSchedule, work_schedule_id):
        raise HTTPException(status_code=404, detail="Régime horaire non trouvé.")


@router.get("/", response_model=List[RuleRead])
def list_rules(_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    return session.exec(select(Rule).order_by(Rule.id.desc())).all()


@router.post("/add", response_model=RuleRead, status_code=201)
def add_rule(payload: RuleCreate, _user: User = Depends(require_user), session: Session = Depends(get_session)):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Le nom de la règle est obligatoire.")
    if not payload.trigger:
        raise HTTPException(status_code=400, detail="Le déclencheur (trigger) est obligatoire.")
    _validate_group_scope(session, payload.trigger, payload.work_schedule_id)
    if payload.work_schedule_id is not None and payload.schedule:
        raise HTTPException(
            status_code=400,
            detail="Une règle de groupe hérite déjà des horaires du régime ; retirez la plage horaire locale.",
        )
    rule = Rule(**payload.model_dump())
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=RuleRead)
def update_rule(rule_id: int, payload: RuleUpdate, _user: User = Depends(require_user), session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée.")
    data = payload.model_dump(exclude_unset=True)
    effective_trigger = data.get("trigger", rule.trigger)
    effective_schedule_id = data.get("work_schedule_id", rule.work_schedule_id)
    _validate_group_scope(session, effective_trigger, effective_schedule_id)
    if effective_schedule_id is not None:
        # Affecter un groupe remplace toujours une ancienne plage locale : garder
        # les deux créerait une intersection implicite difficile à diagnostiquer.
        data["schedule"] = None
    for key, value in data.items():
        setattr(rule, key, value)
    rule.updated_at = datetime.utcnow()
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, _user: User = Depends(require_user), session: Session = Depends(get_session)):
    rule = session.get(Rule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Règle non trouvée.")
    session.delete(rule)
    session.commit()
    return {"message": f"Règle {rule_id} supprimée."}
