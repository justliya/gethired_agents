"""
Standardized Agent to Agent (A2A) server implementation for Job Search AI Assistant.
This module provides a FastAPI server implementation following Google ADK standards.
"""

import os
import json
import inspect
import re
from typing import Dict, Any, Callable, Optional, List, Union

from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Job Search specific models
class JobSearchRequest(BaseModel):
    """Request model for job search - only requires user_id."""
    user_id: str = Field(..., description="Firebase user ID for personalized job search")

# Job Listing Models
class JobListing(BaseModel):
    listingNumber: Union[int, str]
    title: Optional[str] = "Not specified"
    company: Optional[str] = "Not specified"
    location: Optional[str] = "Not specified"
    salary: Optional[str] = "Not specified"
    datePosted: Optional[str] = "Not specified"
    description: Optional[str] = "Not specified"
    qualifications: List[str] = []
    benefits: List[str] = []
    jobLink: Optional[str] = "Not specified"
    easyApply: Union[bool, str] = False

class JobListings(BaseModel):
    jobs: List[JobListing]

# Company Research Models
class CompanyOverview(BaseModel):
    name: Optional[str] = "Not specified"
    id: Optional[str] = "Not specified"
    industry: Optional[str] = "Not specified"
    size: Optional[str] = "Not specified"
    founded: Union[int, str, None] = "Not specified"
    headquarters: Optional[str] = "Not specified"
    website: Optional[str] = "Not specified"
    stockSymbol: Optional[str] = "Not specified"
    logoUrl: Optional[str] = "Not specified"

class CEORating(BaseModel):
    rating: Union[float, int, str, None] = "Not specified"
    name: Optional[str] = "Not specified"

class DetailedBreakdown(BaseModel):
    workLifeBalance: Union[float, int, str, None] = "Not specified"
    cultureAndValues: Union[float, int, str, None] = "Not specified"
    compensationAndBenefits: Union[float, int, str, None] = "Not specified"
    careerOpportunities: Union[float, int, str, None] = "Not specified"
    seniorManagement: Union[float, int, str, None] = "Not specified"
    businessOutlook: Union[float, int, str, None] = "Not specified"

class Ratings(BaseModel):
    overall: Union[float, int, str, None] = "Not specified"
    reviewCount: Union[int, str, None] = "Not specified"
    ceo: CEORating
    recommendToFriend: Union[int, str, None] = "Not specified"
    detailedBreakdown: DetailedBreakdown

class SalaryRange(BaseModel):
    min: Union[int, str, None] = "Not specified"
    max: Union[int, str, None] = "Not specified"
    median: Optional[Union[int, str, None]] = "Not specified"

class AdditionalPay(BaseModel):
    min: Union[int, str, None] = "Not specified"
    max: Union[int, str, None] = "Not specified"

class SalaryEstimates(BaseModel):
    title: Optional[str] = "Not specified"
    baseRange: SalaryRange
    additionalPay: AdditionalPay
    totalCompensation: SalaryRange
    confidenceLevel: Optional[str] = "Not specified"
    dataPoints: Union[int, str, None] = "Not specified"

class RecentInsight(BaseModel):
    title: Optional[str] = "Not specified"
    location: Optional[str] = "Not specified"
    duration: Optional[str] = "Not specified"
    snippet: Optional[str] = "Not specified"

class ReviewsSummary(BaseModel):
    link: Optional[str] = "Not specified"
    pros: List[str] = []
    cons: List[str] = []
    recentInsight: RecentInsight

class InterviewIntelligence(BaseModel):
    difficultyLevel: Optional[str] = "Not specified"
    process: Optional[str] = "Not specified"
    timeline: Optional[str] = "Not specified"
    successRate: Union[int, str, None] = "Not specified"
    commonQuestions: List[str] = []
    tips: List[str] = []

class Competitor(BaseModel):
    name: Optional[str] = "Not specified"
    id: Optional[str] = "Not specified"

class Award(BaseModel):
    title: Optional[str] = "Not specified"
    year: Union[int, str, None] = "Not specified"

class StrategicAssessment(BaseModel):
    strengths: List[str] = []
    concerns: List[str] = []
    recommendation: Optional[str] = "Not specified"

class CompanyResearch(BaseModel):
    companyOverview: CompanyOverview
    ratings: Ratings
    salaryEstimates: SalaryEstimates
    reviewsSummary: ReviewsSummary
    interviewIntelligence: InterviewIntelligence
    competitors: List[Competitor] = []
    officeLocations: List[str] = []
    awards: List[Award] = []
    strategicAssessment: StrategicAssessment

class JobSearchResponse(BaseModel):
    """Response model for job search results."""
    job_listings: JobListings
    company_research: CompanyResearch

def create_agent_server(
    name: str, 
    description: str, 
    task_manager: Any, 
    endpoints: Optional[Dict[str, Callable]] = None,
    well_known_path: Optional[str] = None
) -> FastAPI:
    """
    Create a FastAPI server for the job search agent following A2A protocol.
    
    Args:
        name: The name of the agent
        description: A description of the agent's functionality
        task_manager: The TaskManager instance for handling tasks
        endpoints: Optional dictionary of additional endpoints to register
        well_known_path: Optional path to the .well-known directory
        
    Returns:
        A configured FastAPI application
    """
    app = FastAPI(title=f"{name} - Job Search AI Assistant", description=description)
    
    # Add CORS middleware 
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    
    # Create .well-known directory if it doesn't exist
    if well_known_path is None:
        module_path = inspect.getmodule(inspect.stack()[1][0]).__file__
        well_known_path = os.path.join(os.path.dirname(module_path), ".well-known")
    
    os.makedirs(well_known_path, exist_ok=True)
    
    # Generate agent.json if it doesn't exist
    agent_json_path = os.path.join(well_known_path, "agent.json")
    if not os.path.exists(agent_json_path):
        endpoint_names = ["run-job-search"]
        if endpoints:
            endpoint_names.extend(endpoints.keys())
        
        agent_metadata = {
            "name": name,
            "description": description,
            "endpoints": endpoint_names,
            "version": "1.0.0",
            "capabilities": ["job_search", "profile_analysis", "company_research"],
            "sub_agents": ["profile_agent", "listing_search_agent", "company_research_agent"]
        }
        
        with open(agent_json_path, "w") as f:
            json.dump(agent_metadata, f, indent=2)
    
    # Utility functions
    def unwrap_json_string(json_block: Optional[str]) -> Any:
        """Extract and parse JSON from agent output strings."""
        if not json_block:
            return None
        try:
            # Remove markdown code blocks if present
            clean_json = re.sub(r"^```(?:json)?\n|```$", "", json_block.strip())
            return json.loads(clean_json)
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Raw content: {json_block}")
            return None
    
    def create_default_response() -> Dict[str, Any]:
        """Create a default response structure when data is missing."""
        return {
            "job_listings": {
                "jobs": []
            },
            "company_research": {
                "companyOverview": {
                    "name": "N/A",
                    "id": "N/A",
                    "industry": "N/A",
                    "size": "N/A",
                    "founded": 2000,
                    "headquarters": "N/A",
                    "website": "N/A",
                    "stockSymbol": "N/A",
                    "logoUrl": "N/A"
                },
                "ratings": {
                    "overall": 0.0,
                    "reviewCount": 0,
                    "ceo": {
                        "rating": 0.0,
                        "name": "N/A"
                    },
                    "recommendToFriend": 0,
                    "detailedBreakdown": {
                        "workLifeBalance": 0.0,
                        "cultureAndValues": 0.0,
                        "compensationAndBenefits": 0.0,
                        "careerOpportunities": 0.0,
                        "seniorManagement": 0.0,
                        "businessOutlook": 0.0
                    }
                },
                "salaryEstimates": {
                    "title": "N/A",
                    "baseRange": {
                        "min": 0,
                        "max": 0,
                        "median": 0
                    },
                    "additionalPay": {
                        "min": 0,
                        "max": 0
                    },
                    "totalCompensation": {
                        "min": 0,
                        "max": 0
                    },
                    "confidenceLevel": "low",
                    "dataPoints": 0
                },
                "reviewsSummary": {
                    "link": "N/A",
                    "pros": [],
                    "cons": [],
                    "recentInsight": {
                        "title": "N/A",
                        "location": "N/A",
                        "duration": "N/A",
                        "snippet": "N/A"
                    }
                },
                "interviewIntelligence": {
                    "difficultyLevel": "unknown",
                    "process": "N/A",
                    "timeline": "N/A",
                    "successRate": 0,
                    "commonQuestions": [],
                    "tips": []
                },
                "competitors": [],
                "officeLocations": [],
                "awards": [],
                "strategicAssessment": {
                    "strengths": [],
                    "concerns": [],
                    "recommendation": "N/A"
                }
            }
        }
    
    # Main job search endpoint
    @app.post("/run-job-search", response_model=JobSearchResponse)
    async def run_job_search(request: JobSearchRequest = Body(...)):
        """
        Single endpoint that runs the complete job search workflow:
        1. Fetches user preferences from Firebase
        2. Searches for matching jobs
        3. Performs company research on found jobs
        """
        try:
            print(f"\n>>> Running Job Search for User: {request.user_id}")
            
            # Prepare context with user_id
            context = {"user_id": request.user_id}
            
            # Create the message for the agent
            message = f"Run a complete job search for user ID: {request.user_id}"
            
            # Process through task manager
            result = await task_manager.process_task(message, context)
            
            # Extract the data from the result
            if result["status"] == "success" and "data" in result:
                # Try to extract job listings and company research from the response
                response_data = result.get("data", {})
                
                # If the response contains the structured data directly
                if "job_listings" in response_data and "company_research" in response_data:
                    return JobSearchResponse(
                        job_listings=response_data["job_listings"],
                        company_research=response_data["company_research"]
                    )
                
                # Otherwise, try to parse from the message
                if result.get("message"):
                    # Attempt to extract JSON from the message
                    message_parsed = unwrap_json_string(result["message"])
                    if message_parsed:
                        default_response = create_default_response()
                        
                        if "job_listings" in message_parsed:
                            default_response["job_listings"] = message_parsed["job_listings"]
                        
                        if "company_research" in message_parsed:
                            default_response["company_research"] = message_parsed["company_research"]
                        
                        return JobSearchResponse(**default_response)
            
            # Return default structure if parsing fails
            default_response = create_default_response()
            return JobSearchResponse(**default_response)
            
        except Exception as e:
            print(f">>> Error in job search workflow: {str(e)}")
            # Return default structure on error
            default_response = create_default_response()
            return JobSearchResponse(**default_response)
    
    # Metadata endpoint
    @app.get("/.well-known/agent.json")
    async def get_metadata():
        """Retrieve the agent metadata."""
        with open(agent_json_path, "r") as f:
            return JSONResponse(content=json.load(f))
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": name}
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Welcome endpoint."""
        return {
            "message": f"Welcome to {name} - Job Search AI Assistant",
            "version": "1.0.0",
            "endpoints": ["/run-job-search", "/health", "/.well-known/agent.json", "/docs"]
        }
    
    # Register additional endpoints if provided
    if endpoints:
        for path, handler in endpoints.items():
            app.add_api_route(f"/{path}", handler, methods=["POST"])
    
    return app