from .base import IntakeQuestion, Persona
from .fitness import FITNESS_PERSONA

PERSONAS: dict[str, Persona] = {
    FITNESS_PERSONA.domain: FITNESS_PERSONA,
}
