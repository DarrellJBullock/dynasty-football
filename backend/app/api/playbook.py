import dataclasses

from fastapi import APIRouter

from app.schemas import PlaybookOut
from app.sim.playbook import DEFENSE, OFFENSE

router = APIRouter(tags=["playbook"])


@router.get("/playbook", response_model=PlaybookOut)
def playbook():
    """The named offensive plays and defensive calls every team runs."""
    return PlaybookOut(offense=[dataclasses.asdict(p) for p in OFFENSE],
                       defense=[dataclasses.asdict(p) for p in DEFENSE])
