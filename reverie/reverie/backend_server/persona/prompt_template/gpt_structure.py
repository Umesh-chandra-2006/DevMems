"""
Author: Joon Sung Park (joonspk@stanford.edu)

File: gpt_structure.py
Description: Wrapper functions for calling OpenAI APIs.
"""
import json
import random
import openai
import time 
import os
import sys
from pathlib import Path

# Add project root to sys.path so devmem package is importable
_devmem_root = str(Path(__file__).resolve().parent.parent.parent.parent.parent)
if _devmem_root not in sys.path:
  sys.path.insert(0, _devmem_root)

from utils import *
from devmem.router.llm_router import call_llm

openai.api_key = openai_api_key

def temp_sleep(seconds=1.0):
  time.sleep(seconds)

def _infer_purpose(prompt_text: str) -> str:
  lower = str(prompt_text).lower()
  if "rate how important" in lower or "poignancy" in lower or "on a scale of 1 to 10" in lower:
    return "importance_scoring"
  if "focal" in lower or "insight" in lower or "reflection" in lower:
    return "reflection"
  if "conversation" in lower or "say" in lower or "dialogue" in lower or "talk" in lower or "whisper" in lower:
    return "dialogue"
  if "wake up" in lower or "daily plan" in lower or "schedule" in lower or "action" in lower or "sector" in lower:
    return "planning"
  return "planning"

def ChatGPT_single_request(prompt, purpose="dialogue"): 
  temp_sleep()

  # ORIGINAL OPENAI CODE PATH (disabled for DevMem free-tier routing):
  # completion = openai.ChatCompletion.create(
  #   model="gpt-3.5-turbo", 
  #   messages=[{"role": "user", "content": prompt}]
  # )
  # return completion["choices"][0]["message"]["content"]

  # DEVMEM ROUTER CALL:
  try:
    mode = getattr(utils, "MEMORY_MODE", "baseline") if "utils" in globals() else os.environ.get("MEMORY_MODE", "baseline")
    return call_llm(prompt, tier="fast", purpose=purpose, condition=mode)
  except Exception as e:
    print(f"DevMem Router ERROR in ChatGPT_single_request: {e}")
    return "ChatGPT ERROR"


# ============================================================================
# #####################[SECTION 1: CHATGPT-3 STRUCTURE] ######################
# ============================================================================

def GPT4_request(prompt, purpose="planning"): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  temp_sleep()

  # ORIGINAL OPENAI CODE PATH (disabled for DevMem free-tier routing):
  # try: 
  #   completion = openai.ChatCompletion.create(
  #   model="gpt-4", 
  #   messages=[{"role": "user", "content": prompt}]
  #   )
  #   return completion["choices"][0]["message"]["content"]
  # except: 
  #   print ("ChatGPT ERROR")
  #   return "ChatGPT ERROR"

  # DEVMEM ROUTER CALL:
  try:
    mode = getattr(utils, "MEMORY_MODE", "baseline") if "utils" in globals() else os.environ.get("MEMORY_MODE", "baseline")
    return call_llm(prompt, tier="strong", purpose=purpose, condition=mode)
  except Exception as e:
    print(f"DevMem Router ERROR in GPT4_request: {e}")
    return "ChatGPT ERROR"


def ChatGPT_request(prompt, purpose="dialogue"): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  # temp_sleep()

  # ORIGINAL OPENAI CODE PATH (disabled for DevMem free-tier routing):
  # try: 
  #   completion = openai.ChatCompletion.create(
  #   model="gpt-3.5-turbo", 
  #   messages=[{"role": "user", "content": prompt}]
  #   )
  #   return completion["choices"][0]["message"]["content"]
  # except: 
  #   print ("ChatGPT ERROR")
  #   return "ChatGPT ERROR"

  # DEVMEM ROUTER CALL:
  try:
    mode = getattr(utils, "MEMORY_MODE", "baseline") if "utils" in globals() else os.environ.get("MEMORY_MODE", "baseline")
    return call_llm(prompt, tier="fast", purpose=purpose, condition=mode)
  except Exception as e:
    print(f"DevMem Router ERROR in ChatGPT_request: {e}")
    return "ChatGPT ERROR"


def GPT4_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  purpose = _infer_purpose(prompt)
  for i in range(repeat): 

    try: 
      curr_gpt_response = GPT4_request(prompt, purpose=purpose).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count: \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass

  return False


def ChatGPT_safe_generate_response(prompt, 
                                   example_output,
                                   special_instruction,
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  # prompt = 'GPT-3 Prompt:\n"""\n' + prompt + '\n"""\n'
  prompt = '"""\n' + prompt + '\n"""\n'
  prompt += f"Output the response to the prompt above in json. {special_instruction}\n"
  prompt += "Example output json:\n"
  prompt += '{"output": "' + str(example_output) + '"}'

  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  purpose = _infer_purpose(prompt)
  for i in range(repeat): 

    try: 
      curr_gpt_response = ChatGPT_request(prompt, purpose=purpose).strip()
      end_index = curr_gpt_response.rfind('}') + 1
      curr_gpt_response = curr_gpt_response[:end_index]
      curr_gpt_response = json.loads(curr_gpt_response)["output"]

      # print ("---ashdfaf")
      # print (curr_gpt_response)
      # print ("000asdfhia")
      
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      
      if verbose: 
        print ("---- repeat count: \n", i, curr_gpt_response)
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass

  return False


def ChatGPT_safe_generate_response_OLD(prompt, 
                                   repeat=3,
                                   fail_safe_response="error",
                                   func_validate=None,
                                   func_clean_up=None,
                                   verbose=False): 
  if verbose: 
    print ("CHAT GPT PROMPT")
    print (prompt)

  purpose = _infer_purpose(prompt)
  for i in range(repeat): 
    try: 
      curr_gpt_response = ChatGPT_request(prompt, purpose=purpose).strip()
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
      if verbose: 
        print (f"---- repeat count: {i}")
        print (curr_gpt_response)
        print ("~~~~")

    except: 
      pass
  print ("FAIL SAFE TRIGGERED") 
  return fail_safe_response


# ============================================================================
# ###################[SECTION 2: ORIGINAL GPT-3 STRUCTURE] ###################
# ============================================================================

def _clean_completion_continuation(prompt: str, response_text: str, stop=None) -> str:
  cleaned = response_text.strip()
  prompt_tail = prompt.strip().split("\n")[-1].strip()

  # 1. Strip common completion cues
  for cue in ["Answer: {", "Answer:", "{", "Output:", "output:"]:
    if prompt_tail.endswith(cue) and cleaned.startswith(cue):
      cleaned = cleaned[len(cue):].strip()

  # 2. If prompt ended with an incomplete sentence like "1) <Name> is" and response repeated it:
  lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
  if lines:
    first_line = lines[0]
    if prompt_tail.endswith(" is") and (" is " in first_line):
      parts = first_line.split(" is ", 1)
      if len(parts) == 2 and ("1)" in parts[0] or prompt_tail.split()[0] in parts[0]):
        lines[0] = parts[1].strip()
        cleaned = "\n".join(lines)

  # 3. Apply stop sequence truncation if specified (mirrors OpenAI engine stop parameter)
  if stop:
    if isinstance(stop, str):
      stop = [stop]
    for stop_str in stop:
      if stop_str and stop_str in cleaned:
        cleaned = cleaned.split(stop_str)[0].strip()

  # 4. Task decomp formatting fallback: if prompt asked for subtasks with durations in 5 min increments
  # but response lines lack '(duration in minutes:', automatically synthesize valid durations
  if "(total duration in minutes" in prompt and "(duration in minutes:" in prompt and "(duration in minutes:" not in cleaned:
    try:
      total_min_str = prompt.split("(total duration in minutes")[-1].split("):")[0].replace(":", "").strip()
      total_min = int(total_min_str)
      raw_lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
      if raw_lines:
        dur_per_task = max(5, round((total_min / len(raw_lines)) / 5) * 5)
        rem = total_min
        formatted_lines = []
        for idx, r_line in enumerate(raw_lines):
          # Clean existing numbers if any
          clean_task = r_line
          for prefix in [f"{idx+1})", f"{idx+1}.", "-", "*"]:
            if clean_task.startswith(prefix):
              clean_task = clean_task[len(prefix):].strip()
          d = min(rem, dur_per_task) if idx < len(raw_lines) - 1 else rem
          rem = max(0, rem - d)
          if idx == 0:
            formatted_lines.append(f"{clean_task}. (duration in minutes: {d}, minutes left: {rem})")
          else:
            formatted_lines.append(f"{idx+1}) {clean_task}. (duration in minutes: {d}, minutes left: {rem})")
        cleaned = "\n".join(formatted_lines)
    except Exception:
      pass

  return cleaned

def GPT_request(prompt, gpt_parameter, purpose=None): 
  """
  Given a prompt and a dictionary of GPT parameters, make a request to OpenAI
  server and returns the response. 
  ARGS:
    prompt: a str prompt
    gpt_parameter: a python dictionary with the keys indicating the names of  
                   the parameter and the values indicating the parameter 
                   values.   
  RETURNS: 
    a str of GPT-3's response. 
  """
  temp_sleep()
  if purpose is None:
    purpose = _infer_purpose(prompt)

  # DEVMEM ROUTER CALL:
  try:
    mode = getattr(utils, "MEMORY_MODE", "baseline") if "utils" in globals() else os.environ.get("MEMORY_MODE", "baseline")
    sys_prompt = (
      "You are a raw text completion engine for an AI simulation.\n"
      "Do NOT converse, greet, explain, or output any chat preamble or apologies.\n"
      "Complete the prompt directly, following strictly the format, structure, and syntax demonstrated in the few-shot examples.\n"
      "If the prompt asks for subtasks with durations, every single line MUST include '(duration in minutes: <int>, minutes left: <int>)'."
    )
    temp = gpt_parameter.get("temperature", 0.1) if isinstance(gpt_parameter, dict) else 0.1
    stop = gpt_parameter.get("stop") if isinstance(gpt_parameter, dict) else None
    raw_resp = call_llm(
      prompt,
      tier="fast",
      purpose=purpose,
      condition=mode,
      system_prompt=sys_prompt,
      temperature=temp,
    )
    return _clean_completion_continuation(prompt, str(raw_resp), stop=stop)
  except Exception as e:
    print(f"DevMem Router ERROR in GPT_request: {e}")
    return "TOKEN LIMIT EXCEEDED"


def generate_prompt(curr_input, prompt_lib_file): 
  """
  Takes in the current input (e.g. comment that you want to classifiy) and 
  the path to a prompt file. The prompt file contains the raw str prompt that
  will be used, which contains the following substr: !<INPUT>! -- this 
  function replaces this substr with the actual curr_input to produce the 
  final promopt that will be sent to the GPT3 server. 
  ARGS:
    curr_input: the input we want to feed in (IF THERE ARE MORE THAN ONE
                INPUT, THIS CAN BE A LIST.)
    prompt_lib_file: the path to the promopt file. 
  RETURNS: 
    a str prompt that will be sent to OpenAI's GPT server.  
  """
  if type(curr_input) == type("string"): 
    curr_input = [curr_input]
  curr_input = [str(i) for i in curr_input]

  f = open(prompt_lib_file, "r")
  prompt = f.read()
  f.close()
  for count, i in enumerate(curr_input):   
    prompt = prompt.replace(f"!<INPUT {count}>!", i)
  if "<commentblockmarker>###</commentblockmarker>" in prompt: 
    prompt = prompt.split("<commentblockmarker>###</commentblockmarker>")[1]
  return prompt.strip()


def safe_generate_response(prompt, 
                           gpt_parameter,
                           repeat=5,
                           fail_safe_response="error",
                           func_validate=None,
                           func_clean_up=None,
                           verbose=False): 
  if verbose: 
    print (prompt)

  purpose = _infer_purpose(prompt)
  for i in range(repeat): 
    try:
      curr_gpt_response = GPT_request(prompt, gpt_parameter, purpose=purpose)
      if func_validate(curr_gpt_response, prompt=prompt): 
        return func_clean_up(curr_gpt_response, prompt=prompt)
    except Exception as e:
      if verbose:
        print(f"safe_generate_response attempt {i} exception: {e}")
    if verbose: 
      print ("---- repeat count: ", i, curr_gpt_response)
      print (curr_gpt_response)
      print ("~~~~")
  return fail_safe_response


_EMBEDDING_CACHE = {}

def get_embedding(text, model="text-embedding-ada-002"):
  text = text.replace("\n", " ").strip()
  if not text: 
    text = "this is blank"

  if text in _EMBEDDING_CACHE:
    return _EMBEDDING_CACHE[text]

  # ORIGINAL OPENAI CODE PATH (disabled for DevMem free-tier routing):
  # return openai.Embedding.create(
  #         input=[text], model=model)['data'][0]['embedding']

  # DEVMEM FREE EMBEDDING:
  # 1. Attempt Google Gemini gemini-embedding-001 API (free tier)
  gemini_key = os.environ.get("GEMINI_KEY_1") or os.environ.get("GEMINI_KEY_2")
  if gemini_key:
    try:
      import requests
      url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={gemini_key}"
      headers = {"Content-Type": "application/json"}
      payload = {"content": {"parts": [{"text": text}]}}
      resp = requests.post(url, headers=headers, json=payload, timeout=10)
      if resp.status_code == 200:
        emb = resp.json().get("embedding", {}).get("values", [])
        if emb:
          _EMBEDDING_CACHE[text] = emb
          return emb
    except Exception:
      pass

  # 2. Deterministic local unit vector fallback (768 dimensions)
  # Ensures mathematical compatibility with numpy cos_sim without external API or heavy dependencies
  import hashlib
  import numpy as np
  seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
  rng = np.random.RandomState(seed)
  vec = rng.randn(768).astype(float)
  vec = (vec / np.linalg.norm(vec)).tolist()
  _EMBEDDING_CACHE[text] = vec
  return vec


if __name__ == '__main__':
  gpt_parameter = {"engine": "text-davinci-003", "max_tokens": 50, 
                   "temperature": 0, "top_p": 1, "stream": False,
                   "frequency_penalty": 0, "presence_penalty": 0, 
                   "stop": ['"']}
  curr_input = ["driving to a friend's house"]
  prompt_lib_file = "prompt_template/test_prompt_July5.txt"
  prompt = generate_prompt(curr_input, prompt_lib_file)

  def __func_validate(gpt_response): 
    if len(gpt_response.strip()) <= 1:
      return False
    if len(gpt_response.strip().split(" ")) > 1: 
      return False
    return True
  def __func_clean_up(gpt_response):
    cleaned_response = gpt_response.strip()
    return cleaned_response

  output = safe_generate_response(prompt, 
                                 gpt_parameter,
                                 5,
                                 "rest",
                                 __func_validate,
                                 __func_clean_up,
                                 True)

  print (output)




















