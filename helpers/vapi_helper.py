import os
import jwt
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pytz
import httpx
import asyncio
from models.auth import User


load_dotenv()



vapi_api_key = os.environ["VAPI_API_KEY"]
vapi_org_id = os.environ["VAPI_ORG_ID"]




# Debug: Check if environment variables are loaded correctly
print("VAPI_API_KEY:", os.getenv("VAPI_API_KEY"))
print("VAPI_ORG_ID:", os.getenv("VAPI_ORG_ID"))

def generate_token():
    # payload = {
    #     'orgId': vapi_org_id
    # }
    # expiration = datetime.now(pytz.utc) + timedelta(hours=1)
    # print(expiration)
    # payload['exp'] = expiration

    # key = vapi_api_key
    # print("Key: ", key)
    # token = jwt.encode(payload, key, algorithm='HS256')

    # return token
    return vapi_api_key

async def admin_add_payload(assistant_data):
    print(assistant_data)
    to_return = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": assistant_data.systemPrompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": assistant_data.voice_model if assistant_data.voice_model else "octave" if assistant_data.voice_provider == "hume" else "eleven_flash_v2_5" if assistant_data.voice_provider == "11labs" else "aura" if assistant_data.voice_provider == "deepgram" else "eleven_flash_v2_5",
            **({"speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
                "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
                "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75} if assistant_data.voice_provider == "11labs" else {})
        },
        "firstMessageMode": "assistant-speaks-first",
        "hipaaEnabled": assistant_data.hipaaEnabled if hasattr(assistant_data, 'hipaaEnabled') else False,
        "clientMessages": assistant_data.clientMessages,
        "serverMessages": assistant_data.serverMessages,
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": assistant_data.maxDurationSeconds if hasattr(assistant_data, 'maxDurationSeconds') else 600,
        "backgroundSound": "office",
        "backchannelingEnabled": False,
        "backgroundDenoisingEnabled": False,
        "modelOutputInMessagesEnabled": False,
        "transportConfigurations": [
            {
                "provider": "twilio",
                "timeout": 60,
                "record": False,
                "recordingChannels": "mono"
            }
        ],
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message, 
        "voicemailMessage": assistant_data.voicemailMessage if hasattr(assistant_data, 'voicemailMessage') else "",  # Added voicemailMessage field
        "endCallMessage": assistant_data.endCallMessage if hasattr(assistant_data, 'endCallMessage') else "",  # Added endCallMessage field
        "endCallPhrases": assistant_data.endCallPhrases,
        "metadata": {},
        "analysisPlan": {
            "summaryPrompt": assistant_data.systemPrompt,
            "summaryRequestTimeoutSeconds": 10.5,
            "structuredDataRequestTimeoutSeconds": 10.5,
            "successEvaluationPrompt": assistant_data.successEvaluationPrompt if hasattr(assistant_data, 'successEvaluationPrompt') else "",
            "successEvaluationRubric": "PassFail",
            "successEvaluationRequestTimeoutSeconds": 10.5,
            "structuredDataPrompt": assistant_data.structuredDataPrompt if hasattr(assistant_data, 'structuredDataPrompt') else "",
            "structuredDataSchema": {
                "type": "string",
                "items": {"type": "string"},
                "properties": {},
                "description": "<string>",
                "required": ["<string>"]
            }
        },
        "artifactPlan": {
            "recordingEnabled": assistant_data.audioRecordingEnabled if hasattr(assistant_data, 'audioRecordingEnabled') else True,  # Adjusted to use audioRecordingEnabled field
            "videoRecordingEnabled": assistant_data.videoRecordingEnabled if hasattr(assistant_data, 'videoRecordingEnabled') else False,
            "recordingPath": "<string>"
        },
        "messagePlan": {
            "idleMessages": assistant_data.idleMessages if hasattr(assistant_data, 'idleMessages') else [""],
            "idleMessageMaxSpokenCount": assistant_data.idleMessageMaxSpokenCount if hasattr(assistant_data, 'idleMessageMaxSpokenCount') else 5,
            "idleTimeoutSeconds": assistant_data.idleTimeoutSeconds if hasattr(assistant_data, 'idleTimeoutSeconds') else 17.5
        },
        "startSpeakingPlan": {
            "waitSeconds": 0.4,
            "smartEndpointingEnabled": False,
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.1,
                "onNoPunctuationSeconds": 1.5,
                "onNumberSeconds": 0.5
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.2,
            "backoffSeconds": 1
        },
        "monitorPlan": {
            "listenEnabled": False,
            "controlEnabled": False
        }
    }

    if (assistant_data.forwardingPhoneNumber):
        
        to_return["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]
        
        to_return["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber

    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
        # Await the result of create_query_tool
        tool_response = await create_query_tool(assistant_data.knowledgeBase)
        
        if tool_response is None:
            print("Error: Tool creation failed.")
        else:
            tool_id = tool_response.get("id") 
            
            if not tool_id:
                to_return["model"]["toolIds"] = []
            else:
                to_return["model"]["toolIds"] = [tool_id]
                print(f"Tool ID: {tool_id}")
    else:
        print("No knowledgeBase provided or it's empty. Skipping tool creation.")
        to_return["model"]["toolIds"] = []

    return to_return

async def user_add_payload(assistant_data,user):
    user = await User.filter(id=user.id).first()


    if not assistant_data.languages:
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."
    else:
            languages = ", ".join(assistant_data.languages)
            systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the: **{languages}** languages. Any other language will not be understood, and responses will be given only in these **{languages}** languages."


    print(systemprompt)
    
    if assistant_data.voice_provider == "deepgram":
        voice_model = "aura"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model":voice_model,
        }
    elif assistant_data.voice_provider == "hume":
        # For Hume voices, use the provided voice_model or default to "octave"
        voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
        print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
        print(f"Hume voice - first_message: '{assistant_data.first_message}'")
        print(f"Hume voice - systemPrompt: '{assistant_data.systemPrompt}'")
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
        print(f"Final Hume voice config: {voice}")

    elif assistant_data.voice_provider == "openai":
       # voice_model = "gpt-4o-mini-tts"
        voice = {
            "provider": "openai",
            "voiceId": assistant_data.voice,
            "model": "gpt-4o-mini-tts",
        }
        print(f"Final OpenAI voice config: {voice}")
    else:
        voice_model = "eleven_flash_v2_5"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model":voice_model,
            "speed": assistant_data.speed if assistant_data.speed is not None else 1.0,
            "stability": assistant_data.stability if assistant_data.stability is not None else 0.75,
            "similarityBoost": assistant_data.similarityBoost if assistant_data.similarityBoost is not None else 0.75,
        }
        
        
    user_payload = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": systemprompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": voice,
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
        "endCallPhrases": assistant_data.endCallPhrases,
        "analysisPlan": {\
            "summaryPrompt": assistant_data.systemPrompt,
        },
        # Add speech control parameters for more natural speech patterns
        "startSpeakingPlan": {
            "waitSeconds": 0.8,  # Longer wait before starting to speak
            "smartEndpointingEnabled": True,  # Enable smart endpointing
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.3,  # Longer pause on punctuation
                "onNoPunctuationSeconds": 2.0,  # Longer pause when no punctuation
                "onNumberSeconds": 0.8  # Longer pause on numbers
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.5,  # Longer voice seconds for natural pauses
            "backoffSeconds": 1.5  # Longer backoff for natural breaks
        }
    }

    if assistant_data.forwardingPhoneNumber:
        # print("yes provided"+assistant_data.forwardingPhoneNumber)
        user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
        
        user_payload["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]

    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
        tool_response = await create_query_tool(assistant_data.knowledgeBase)
        
        if tool_response is None:
            print("Error: Tool creation failed.")
        else:
            tool_id = tool_response.get("id") 
            
            if not tool_id:
                user_payload["model"]["toolIds"] = []
            else:
                user_payload["model"]["toolIds"] = [tool_id]
                print(f"Tool ID: {tool_id}")
    else:
        print("No knowledgeBase provided or it's empty. Skipping tool creation.")
        user_payload["model"]["toolIds"] = []
    
    # Debug: Print final payload for Hume voices
    if assistant_data.voice_provider == "hume":
        print(f"Final VAPI payload for Hume voice: {user_payload}")
        print(f"First message length: {len(assistant_data.first_message) if assistant_data.first_message else 0}")
        print(f"System prompt length: {len(assistant_data.systemPrompt) if assistant_data.systemPrompt else 0}")
        
        # Additional debugging for voice configuration
        print(f"Hume voice provider: {assistant_data.voice_provider}")
        print(f"Hume voice model: {voice_model}")
        print(f"Hume voice ID: {assistant_data.voice}")
        print(f"Hume firstMessageMode: {user_payload.get('firstMessageMode')}")
        print(f"Hume silenceTimeoutSeconds: {user_payload.get('silenceTimeoutSeconds')}")
        print(f"Hume maxDurationSeconds: {user_payload.get('maxDurationSeconds')}")
        
        # Debug speech control parameters
        start_speaking_plan = user_payload.get('startSpeakingPlan', {})
        stop_speaking_plan = user_payload.get('stopSpeakingPlan', {})
        print(f"Hume startSpeakingPlan - waitSeconds: {start_speaking_plan.get('waitSeconds')}")
        print(f"Hume startSpeakingPlan - smartEndpointingEnabled: {start_speaking_plan.get('smartEndpointingEnabled')}")
        print(f"Hume startSpeakingPlan - transcriptionEndpointingPlan: {start_speaking_plan.get('transcriptionEndpointingPlan')}")
        print(f"Hume stopSpeakingPlan - voiceSeconds: {stop_speaking_plan.get('voiceSeconds')}")
        print(f"Hume stopSpeakingPlan - backoffSeconds: {stop_speaking_plan.get('backoffSeconds')}")
    
    return user_payload


async def create_query_tool(file_ids, tool_name="Query-Tool"):
    url = "https://api.vapi.ai/tool/"
    headers = {
        "Authorization": f"Bearer {vapi_api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "type": "query",
        "function": {"name": tool_name},
        "knowledgeBases": [
            {
                "provider": "google",
                "name": "product-kb",
                "description": "Use this knowledge base when the user asks or queries about the product or services",
                "fileIds": file_ids
            }
        ]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=data)
            if response.status_code in [200, 201]:
                # print("Tool created successfully!", response.json())
                return response.json() 
            else:
                # print(f"Error creating tool: {response.status_code} - {response.text}")
                return None

    except httpx.RequestError as e:
        print(f"An error occurred while requesting the tool creation: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


data = {
    "user@example.com": {
        "username": "user@example.com",
        "full_name": "User Example",
        "email": "user@example.com",
        "hashed_password": "fakehashedsecret",
        "disabled": False,
    }
}


def get_headers():
    token = generate_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    return headers

def get_file_headers():
    token = generate_token()
    headers = {
        "Authorization": f"Bearer {token}",
    }
    return headers





async def assistant_payload(assistant_data,company_id):
    
    assigned_languages = await AssignedLanguage.filter(company_id=company_id).first()

    if assigned_languages and assigned_languages.language:
    
        if isinstance(assigned_languages.language, list):
            languages = ", ".join(assigned_languages.language)
        else:
            languages = assigned_languages.language
        
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in the : **{languages}** languages. Any other language will not be understood, and responses will be given only in these languages."
    else:
        systemprompt = f"{assistant_data.systemPrompt} Please note, you can only communicate in **English**. Any other language will not be understood, and responses will be in English only."

    
    if assistant_data.voice_provider == "deepgram":
        voice_model = "aura"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
    elif assistant_data.voice_provider == "hume":
        # For Hume voices, use the provided voice_model or default to "octave"
        voice_model = assistant_data.voice_model if assistant_data.voice_model else "octave"
        print(f"Hume voice configuration - voice_model: {voice_model}, voiceId: {assistant_data.voice}")
        print(f"Hume voice - first_message: '{assistant_data.first_message}'")
        print(f"Hume voice - systemPrompt: '{assistant_data.systemPrompt}'")
        
        # Validate Hume voice ID format
        if not assistant_data.voice or len(assistant_data.voice) < 10:
            print(f"WARNING: Hume voice ID appears invalid: {assistant_data.voice}")
        
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
        }
        print(f"Final Hume voice config: {voice}")
        
        # Additional debugging for Hume voice issues
        print(f"Hume voice ID length: {len(assistant_data.voice) if assistant_data.voice else 0}")
        print(f"Hume voice ID format check: {assistant_data.voice and '-' in assistant_data.voice}")
        
        # Check if voice ID is a valid UUID format
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        is_valid_uuid = bool(uuid_pattern.match(assistant_data.voice)) if assistant_data.voice else False
        print(f"Hume voice ID UUID format check: {is_valid_uuid}")
        
        # Check if voice ID is a valid UUID format
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        is_valid_uuid = bool(uuid_pattern.match(assistant_data.voice)) if assistant_data.voice else False
        print(f"Hume voice ID UUID format check: {is_valid_uuid}")
    else:
        voice_model = "eleven_flash_v2_5"
        voice = {
            "provider": assistant_data.voice_provider,
            "voiceId": assistant_data.voice,
            "model": voice_model,
            "speed": assistant_data.speed or 0,
            "stability": assistant_data.stability,
            "similarityBoost": assistant_data.similarityBoost,
        }
        
        
    user_payload = {
        "transcriber": {
            "provider": assistant_data.transcribe_provider,
            "model": assistant_data.transcribe_model,
            "language": assistant_data.transcribe_language,
        },
        "model": {
            "messages": [
                {
                    "content": systemprompt,
                    "role": "system"
                }
            ],
            "provider": assistant_data.provider,
            "model": assistant_data.model,
            "temperature": assistant_data.temperature,
            "knowledgeBase": {
                "provider": "canonical",
                "topK": 5,
                "fileIds": assistant_data.knowledgeBase
            },
            "maxTokens": assistant_data.maxTokens,
        },
        "voice": voice,
        "name": assistant_data.name,
        "firstMessage": assistant_data.first_message,
        "firstMessageMode": "assistant-speaks-first",
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 600,
        "endCallPhrases": assistant_data.endCallPhrases,
        "analysisPlan": {
            "summaryPrompt": assistant_data.systemPrompt,
        },
        # Add speech control parameters for more natural speech patterns
        "startSpeakingPlan": {
            "waitSeconds": 0.8,  # Longer wait before starting to speak
            "smartEndpointingEnabled": True,  # Enable smart endpointing
            "transcriptionEndpointingPlan": {
                "onPunctuationSeconds": 0.3,  # Longer pause on punctuation
                "onNoPunctuationSeconds": 2.0,  # Longer pause when no punctuation
                "onNumberSeconds": 0.8  # Longer pause on numbers
            }
        },
        "stopSpeakingPlan": {
            "numWords": 0,
            "voiceSeconds": 0.5,  # Longer voice seconds for natural pauses
            "backoffSeconds": 1.5  # Longer backoff for natural breaks
        }
    }

    if assistant_data.forwardingPhoneNumber:
        # print("yes provided"+assistant_data.forwardingPhoneNumber)
        user_payload["forwardingPhoneNumber"] = assistant_data.forwardingPhoneNumber
        
        user_payload["model"]["tools"] = [
            {
                "type": "transferCall",
                "destinations": [
                    {
                        "type": "number",
                        "number": assistant_data.forwardingPhoneNumber,
                        "description": "Transfer to customer support",
                    }
                ]
            }
        ]

    if assistant_data.knowledgeBase and len(assistant_data.knowledgeBase) > 0:
        tool_response = await create_query_tool(assistant_data.knowledgeBase)
        
        if tool_response is None:
            print("Error: Tool creation failed.")
        else:
            tool_id = tool_response.get("id") 
            
            if not tool_id:
                user_payload["model"]["toolIds"] = []
            else:
                user_payload["model"]["toolIds"] = [tool_id]
                print(f"Tool ID: {tool_id}")
    else:
        print("No knowledgeBase provided or it's empty. Skipping tool creation.")
        user_payload["model"]["toolIds"] = []

    # Debug: Print final payload for Hume voices
    # if assistant_data.voice_provider == "hume":
    #     print(f"Final VAPI payload for Hume voice (assistant_payload): {user_payload}")
    #     print(f"First message length: {len(assistant_data.first_message) if assistant_data.first_message else 0}")
    #     print(f"System prompt length: {len(assistant_data.systemPrompt) if assistant_data.systemPrompt else 0}")
        
        # Additional debugging for voice configuration
        # print(f"Hume voice provider: {assistant_data.voice_provider}")
        # print(f"Hume voice model: {voice_model}")
        # print(f"Hume voice ID: {assistant_data.voice}")
        # print(f"Hume firstMessageMode: {user_payload.get('firstMessageMode')}")
        # print(f"Hume silenceTimeoutSeconds: {user_payload.get('silenceTimeoutSeconds')}")
        # print(f"Hume maxDurationSeconds: {user_payload.get('maxDurationSeconds')}")
        
        # Debug speech control parameters
        start_speaking_plan = user_payload.get('startSpeakingPlan', {})
        stop_speaking_plan = user_payload.get('stopSpeakingPlan', {})
        # print(f"Hume startSpeakingPlan - waitSeconds: {start_speaking_plan.get('waitSeconds')}")
        # print(f"Hume startSpeakingPlan - smartEndpointingEnabled: {start_speaking_plan.get('smartEndpointingEnabled')}")
        # print(f"Hume startSpeakingPlan - transcriptionEndpointingPlan: {start_speaking_plan.get('transcriptionEndpointingPlan')}")
        # print(f"Hume stopSpeakingPlan - voiceSeconds: {stop_speaking_plan.get('voiceSeconds')}")
        # print(f"Hume stopSpeakingPlan - backoffSeconds: {stop_speaking_plan.get('backoffSeconds')}")
    
    return user_payload