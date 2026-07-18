# app/routes/rules_routes.py
"""CRUD du moteur de règles (décision). Lecture VIEWER+, écriture USER/ADMIN.
Les règles sont évaluées à l'ingestion d'événement (services/rule_engine)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime

from app.database import get_session
from app.models.rules import Rule
from app.models.users import User
from app.schemas.rules_schema import RuleCreate, RuleUpdate, RuleRead
from app.middleware.auth_middleware import require_viewer, require_user

router = APIRouter()


@router.get("/", response_model=List[RuleRead])
def list_rules(_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    return session.exec(select(Rule).order_by(Rule.id.desc())).all()


@router.post("/add", response_model=RuleRead, status_code=201)
def add_rule(payload: RuleCreate, _user: User = Depends(require_user), session: Session = Depends(get_session)):
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Le nom de la règle est obligatoire.")
    if not payload.trigger:
        raise HTTPException(status_code=400, detail="Le déclencheur (trigger) est obligatoire.")
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
    for key, value in payload.model_dump(exclude_unset=True).items():
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
