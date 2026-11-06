"""Provider transport. Credentials are server-only and are never returned to the UI."""
import os
from urllib.parse import urlparse
import httpx

PROVIDER=os.getenv('QUERYCRAFT_PROVIDER','ollama')
OLLAMA=os.getenv('OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
MODEL=os.getenv('OPENAI_MODEL','') if PROVIDER=='openai' else os.getenv('QUERYCRAFT_MODEL','llama3.2:3b')
LOCAL=PROVIDER=='ollama' and urlparse(OLLAMA).hostname in ('127.0.0.1','localhost','::1')

def complete(client,messages,schema,max_tokens):
    if PROVIDER=='ollama':
        headers={'Authorization':'Bearer '+os.environ['OLLAMA_API_KEY']} if os.getenv('OLLAMA_API_KEY') else {}
        response=client.post(OLLAMA+'/api/chat',headers=headers,json={'model':MODEL,'messages':messages,'stream':False,'format':schema,'options':{'temperature':0,'num_ctx':8192,'num_predict':max_tokens}})
        response.raise_for_status();data=response.json()
        return {'content':data['message']['content'],'tokens':data.get('eval_count')}
    if PROVIDER=='openai':
        key=os.getenv('OPENAI_API_KEY')
        if not key or not MODEL:raise ValueError('Hosted inference needs server-side OPENAI_API_KEY and OPENAI_MODEL configuration.')
        strict=dict(schema);strict['additionalProperties']=False
        response=client.post('https://api.openai.com/v1/responses',headers={'Authorization':'Bearer '+key},json={'model':MODEL,'input':messages,'store':False,'max_output_tokens':max_tokens,'text':{'format':{'type':'json_schema','name':'querycraft_plan','schema':strict,'strict':True}}})
        response.raise_for_status();data=response.json()
        text=''.join(c.get('text','') for item in data.get('output',[]) if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text')
        if data.get('status')!='completed' or not text:raise ValueError('The hosted model refused or did not complete a structured response. No answer was accepted.')
        return {'content':text,'tokens':data.get('usage',{}).get('output_tokens')}
    raise ValueError('Unsupported model provider. Set QUERYCRAFT_PROVIDER to ollama or openai.')
