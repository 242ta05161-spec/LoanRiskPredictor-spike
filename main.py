from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.orm import sessionmaker, declarative_base

# =========================
# DATABASE SETUP
# =========================

DATABASE_URL = "sqlite:///./fintrust.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class LoanRecord(Base):
    __tablename__ = "loan_records"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    rule_score = Column(Float)
    ml_probability = Column(Float)
    combined_score = Column(Float)
    decision = Column(String)

Base.metadata.create_all(bind=engine)

# =========================
# FASTAPI APP
# =========================

app = FastAPI(title="FinTrust AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# REQUEST MODEL
# =========================

class ApplicantRequest(BaseModel):
    name: str
    age: int
    monthly_income: float
    seasonal_income_variation: float
    credit_score: int
    existing_loans: float
    academic_score: float
    is_student: bool

# =========================
# ML MODEL
# =========================

class LoanMLModel:
    def __init__(self):
        self.model = LogisticRegression()
        self._train()

    def _train(self):
        X = np.array([
            [25, 40000, 0.2, 750, 10000, 0, 0],
            [40, 20000, 0.8, 500, 50000, 0, 0],
            [22, 0, 0.0, 0, 0, 90, 1],
            [35, 60000, 0.1, 800, 5000, 0, 0],
            [30, 15000, 0.7, 580, 20000, 0, 0],
        ])
        y = np.array([0, 1, 1, 0, 1])
        self.model.fit(X, y)

    def predict(self, app):
        features = np.array([[
            app.age,
            app.monthly_income,
            app.seasonal_income_variation,
            app.credit_score,
            app.existing_loans,
            app.academic_score,
            int(app.is_student)
        ]])
        return self.model.predict_proba(features)[0][1]

ml_model = LoanMLModel()

# =========================
# RULE ENGINE
# =========================

def calculate_rule_score(app):
    score = 0
    explanations = []

    if app.credit_score == 0:
        score += 20
        explanations.append("No credit history")
    elif app.credit_score < 600:
        score += 30
        explanations.append("Low credit score")
    elif app.credit_score < 750:
        score += 15
        explanations.append("Moderate credit score")
    else:
        score += 5
        explanations.append("Strong credit profile")

    if app.monthly_income <= 0:
        score += 40
        explanations.append("No stable income")
    elif app.seasonal_income_variation > 0.6:
        score += 20
        explanations.append("Highly seasonal income")
    else:
        score += 5
        explanations.append("Stable income")

    debt_ratio = app.existing_loans / (app.monthly_income + 1)
    if debt_ratio > 5:
        score += 30
        explanations.append("High existing debt")
    else:
        score += 5
        explanations.append("Manageable debt")

    if app.is_student:
        if app.academic_score > 85:
            score -= 15
            explanations.append("Strong academic performance")
        else:
            score += 10
            explanations.append("Low academic performance")

    return max(score, 0), explanations

def final_decision(score):
    if score <= 40:
        return "APPROVED"
    elif score <= 70:
        return "REVIEW MANUALLY"
    else:
        return "REJECTED"

# =========================
# PREDICTION API
# =========================

@app.post("/predict")
def predict(applicant: ApplicantRequest):

    rule_score, explanations = calculate_rule_score(applicant)
    ml_prob = ml_model.predict(applicant)

    combined_score = (0.6 * rule_score) + (0.4 * ml_prob * 100)
    decision = final_decision(combined_score)

    db = SessionLocal()
    db.add(LoanRecord(
        name=applicant.name,
        rule_score=rule_score,
        ml_probability=ml_prob,
        combined_score=combined_score,
        decision=decision
    ))
    db.commit()
    db.close()

    return {
        "name": applicant.name,
        "rule_score": round(rule_score, 2),
        "ml_probability": round(ml_prob, 2),
        "combined_score": round(combined_score, 2),
        "decision": decision,
        "explanations": explanations
    }

# =========================
# ANALYTICS API
# =========================

@app.get("/analytics")
def analytics():
    db = SessionLocal()
    records = db.query(LoanRecord).all()

    total = len(records)
    approved = len([r for r in records if r.decision == "APPROVED"])
    rejected = len([r for r in records if r.decision == "REJECTED"])

    db.close()

    return {
        "total_applications": total,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": round((approved / total * 100), 2) if total else 0
    }