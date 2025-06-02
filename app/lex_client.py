import boto3
import os
from dotenv import load_dotenv

load_dotenv()

bot_id = os.getenv("LEX_BOT_ID")
bot_alias_id = os.getenv("LEX_BOT_ALIAS_ID")
locale_id = os.getenv("LEX_BOT_LOCALE_ID")
region = os.getenv("AWS_REGION")

lex_client = boto3.client("lexv2-runtime", region_name=region)

def get_lex_response(user_id: str, message: str) -> dict:
    try:
        response = lex_client.recognize_text(
            botId=bot_id,
            botAliasId=bot_alias_id,
            localeId=locale_id,
            sessionId=user_id,
            text=message
        )
        print("AWS Lex response:", response)
        return response
    except Exception as e:
        print("Eroare Lex V2:", e)
        return {"messages": [{"content": f"Error: {e}"}]}
