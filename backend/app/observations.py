from models import Observation


def observation(**kwargs) -> dict:
    return Observation(**kwargs).model_dump()
