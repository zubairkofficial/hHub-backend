from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Union

from helper.lead_scoring import LeadScoringService

router = APIRouter()

