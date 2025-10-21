#!/usr/bin/env python3
"""
Job Finder MCP Server — Matches user profiles to job descriptions.
"""

import json
import boto3
import os
import re
import math
from typing import List, Dict, Set
from collections import Counter
from awslabs.mcp_lambda_handler import MCPLambdaHandler

print("Starting MCP server...")

# Initialize MCP handler
mcp = MCPLambdaHandler(name="job-finder", version="1.0.0")

S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
JOB_FOLDER = os.environ.get("JOB_FOLDER", "jobs/")

# --- Utility Functions ---

def normalize_text(text: str) -> List[str]:
    text = re.sub(r"[^\w\s]", " ", text.lower())
    words = text.split()
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "is", "are", "was", "were", "be",
        "been", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "must", "can"
    }
    return [w for w in words if len(w) > 2 and w not in stop_words]

def calculate_semantic_similarity(profile_text: str, job_text: str) -> float:
    try:
        user_words = normalize_text(profile_text)
        job_words = normalize_text(job_text)
        if not user_words or not job_words:
            return 0.0

        all_words = set(user_words + job_words)
        user_freq = Counter(user_words)
        job_freq = Counter(job_words)

        def tfidf_vector(freq, all_words, total_words):
            vec = {}
            for w in all_words:
                tf = freq.get(w, 0) / total_words
                idf = math.log(len(all_words) / (1 + sum(1 for x in all_words if x in freq)))
                vec[w] = tf * idf
            return vec

        uvec = tfidf_vector(user_freq, all_words, len(user_words))
        jvec = tfidf_vector(job_freq, all_words, len(job_words))

        dot = sum(uvec[w] * jvec[w] for w in all_words)
        umag = math.sqrt(sum(v ** 2 for v in uvec.values()))
        jmag = math.sqrt(sum(v ** 2 for v in jvec.values()))

        if umag == 0 or jmag == 0:
            return 0.0

        return dot / (umag * jmag)

    except Exception as e:
        print(f"Similarity error: {e}")
        return 0.0

def extract_skills_from_text(text: str) -> List[str]:
    skills = [
        "python", "excel", "sql", "javascript", "react", "aws", "azure", "data analysis",
        "project management", "machine learning", "environmental science", "renewable energy",
        "communication", "leadership", "sustainability", "green tech", "carbon footprint"
    ]
    text_lower = text.lower()
    return [s for s in skills if s in text_lower]

# --- MCP Tools ---

@mcp.tool()
def listJobs() -> str:
    """List all job postings in the S3 bucket."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=JOB_FOLDER)
        files = [
            {"filename": obj["Key"].replace(JOB_FOLDER, ""), "size": obj["Size"]}
            for obj in response.get("Contents", []) if not obj["Key"].endswith("/")
        ]
        return json.dumps({"jobs": files, "total": len(files)}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
def matchJobsToProfile(profile_text: str, min_similarity: float = 0.3) -> str:
    """Find jobs matching a user's profile or resume text."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=JOB_FOLDER)
        jobs = []

        for obj in response.get("Contents", []):
            if obj["Key"].endswith("/"):
                continue

            file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=obj["Key"])
            content = file_obj["Body"].read().decode("utf-8")

            job_data = json.loads(content) if content.strip().startswith("{") else {"description": content}

            description = job_data.get("description", "")
            title = job_data.get("title", obj["Key"])
            company = job_data.get("company", "Unknown")

            score = calculate_semantic_similarity(profile_text, description)
            if score >= min_similarity:
                jobs.append({
                    "title": title,
                    "company": company,
                    "similarity_score": round(score * 100, 1),
                    "skills_matched": extract_skills_from_text(description),
                    "recommendation": (
                        "🟢 Strong Fit" if score >= 0.7 else
                        "🟡 Moderate Fit" if score >= 0.5 else
                        "🟠 Slight Fit"
                    )
                })

        jobs.sort(key=lambda j: j["similarity_score"], reverse=True)

        return json.dumps({
            "total_matches": len(jobs),
            "matches": jobs,
            "summary": f"Found {len(jobs)} job matches with ≥{min_similarity:.0%} similarity"
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
        
@mcp.tool()
def getJobDetails(job_filename: str) -> str:
    """Return details of a specific job posting given its filename."""
    try:
        s3 = boto3.client("s3")
        key = f"{JOB_FOLDER}{job_filename}"

        file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=key)
        content = file_obj["Body"].read().decode("utf-8")

        # Try to parse JSON, fallback to raw text
        job_data = json.loads(content) if content.strip().startswith("{") else {"description": content}
        return json.dumps(job_data, indent=2)

    except s3.exceptions.NoSuchKey:
        return json.dumps({"error": f"Job '{job_filename}' not found."}, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@mcp.tool()
def generateJobMarketInsights() -> str:
    """Generate simple job trend insights."""
    try:
        s3 = boto3.client("s3")
        response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=JOB_FOLDER)
        descriptions = []

        for obj in response.get("Contents", []):
            if obj["Key"].endswith("/"):
                continue
            file_obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=obj["Key"])
            content = file_obj["Body"].read().decode("utf-8")
            job_data = json.loads(content) if content.strip().startswith("{") else {"description": content}
            descriptions.append(job_data.get("description", ""))

        all_skills = []
        for desc in descriptions:
            all_skills.extend(extract_skills_from_text(desc))
        skill_counts = Counter(all_skills)
        top_skills = skill_counts.most_common(10)

        return json.dumps({
            "total_jobs": len(descriptions),
            "top_skills": dict(top_skills),
            "observation": "Green tech and sustainability roles remain in high demand."
        }, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)
