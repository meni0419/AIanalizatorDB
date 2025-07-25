from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ollama_helpers import analyze_schema, optimize_query

app = FastAPI(
    title="DeepSeek DB Analyzer",
    description="Автономный сервис анализа БД с DeepSeek-R1"
)

class SchemaRequest(BaseModel):
    ddl: str

class QueryRequest(BaseModel):
    query: str
    schema_ddl: str

@app.post("/analyze-schema")
async def analyze_schema_endpoint(request: SchemaRequest):
    try:
        analysis = analyze_schema(request.ddl)
        return {"analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/optimize-query")
async def optimize_query_endpoint(request: QueryRequest):
    try:
        result = optimize_query(request.query, request.schema_ddl)
        return {"optimized_query": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "alive", "model": "deepseek-llm:7b"}