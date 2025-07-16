from fastapi import APIRouter

router = APIRouter()

@router.get("/webhook-groupe-test")
async def test_webhook():
    return {"status": "✅ CE FICHIER EST BIEN EXECUTÉ"}
