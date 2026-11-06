import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx,pytest
import model_client as transport

def test_openai_transport_strict_schema_and_no_secret_in_result(monkeypatch):
    monkeypatch.setattr(transport,'PROVIDER','openai');monkeypatch.setattr(transport,'MODEL','configured-model')
    monkeypatch.setenv('OPENAI_API_KEY','test-not-real-key')
    def respond(request):
        body=json.loads(request.content)
        assert str(request.url)=='https://api.openai.com/v1/responses'
        assert request.headers['authorization']=='Bearer test-not-real-key'
        assert body['store'] is False and body['text']['format']['strict']
        assert body['text']['format']['schema']['additionalProperties'] is False
        return httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"n":1}'}]}],'usage':{'output_tokens':8}})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result=transport.complete(client,[{'role':'user','content':'test'}],{'type':'object','properties':{'n':{'type':'integer'}},'required':['n']},100)
    assert result=={'content':'{"n":1}','tokens':8}

def test_hosted_refusal_not_accepted(monkeypatch):
    monkeypatch.setattr(transport,'PROVIDER','openai');monkeypatch.setattr(transport,'MODEL','configured-model');monkeypatch.setenv('OPENAI_API_KEY','test-only')
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]}))) as client:
        with pytest.raises(ValueError):transport.complete(client,[],{},100)

def test_hosted_missing_configuration_does_not_make_request(monkeypatch):
    monkeypatch.setattr(transport,'PROVIDER','openai');monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    def forbidden(request):raise AssertionError('Network request should not occur')
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        with pytest.raises(ValueError):transport.complete(client,[],{},100)
