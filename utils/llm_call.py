import json
import os
import time
import openai
from google import genai
from google.genai import types
import logging

logger = logging.getLogger("llm_call")
logger.setLevel(logging.INFO)

config_gemini = None

def process_output_json(output: str):
    # output = output.replace("'", '"')
    output = output.replace("True", "true")
    output = output.replace("False", "false")
    output = output.replace("```json", "")
    output = output.replace("```", "")
    output = output.replace("{api_name:", "{\"api_name\":")
    return output

def get_gemini_client():
    client_llm = genai.Client(
        api_key=os.getenv("GEMINI_KEY"),
    )
    return client_llm


def get_openai_client():
    return openai.OpenAI(
        api_key=os.getenv("QWEN_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

def generate_content_gemini(client: genai.Client, prompt: str, search_tool: bool = False, repeat: int = 10):
    global config_gemini
    if search_tool:
        global config_gemini
        if config_gemini is None:
            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )
            config_gemini = types.GenerateContentConfig(
                tools=[grounding_tool]
            )
        one_time_config = config_gemini
    else:
        one_time_config = None

    while repeat > 0:
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=one_time_config,
            )
            res = process_output_json(response.text)
            try:
                res = json.loads(res)
            except Exception as e:
                logger.error(f"Error parsing json: {res}")
                raise e
            return res
        except Exception as e:
            repeat -= 1
            logger.error(f"Error generating content: {e}, have {repeat} repeat times left")
            time.sleep(1)

    logger.error(f"Failed to generate content after repeat")
    return None

def generate_content_openai(client: openai.OpenAI, prompt: str, repeat: int = 10, model = 'qwen-plus', enable_search: bool = False, forced_search: bool = False, output_check: None|dict = None):

    while repeat > 0:
        try:
            extra_body : dict[str, bool | dict] = {"enable_thinking": False}
            if enable_search:
                extra_body["enable_search"] = True
                if forced_search:
                    extra_body["search_options"] = {
                        "forced_search": True,
                        "enable_source": True,
                        "enable_citation": True,
                        "citation_format": "[ref_<number>]",
                        "search_strategy": "turbo",
                    }
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                extra_body=extra_body,
            ) 
            res = response.choices[0].message.content.strip()
            res = process_output_json(res)
            try:
                res = json.loads(res)
            except Exception as e:
                logger.error(f"Error parsing json: {res}")
                raise e
            if output_check:
                for key, value in output_check.items():
                    if key not in res:
                        logger.error(f"Output check failed: {key} not found in {res}")
                        raise ValueError(f"Output check failed: {key} not found in {res}")
            return res
        except Exception as e:
            repeat -= 1
            logger.error(f"Error generating content: {e}, have {repeat} repeat times left")
            time.sleep(1)

    logger.error(f"Failed to generate content after repeat")
    return None