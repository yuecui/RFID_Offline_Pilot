from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from rfid_formats import parse_session
from s3_store import S3SessionStore

class FakeS3:
    def __init__(self): self.puts=[]
    def put_object(self, **kwargs): self.puts.append(kwargs)


def test_conditional_put_sse_s3():
    file = open("examples/sample_readings.csv","rb").read()
    parsed = parse_session(file,"s.csv")
    fake = FakeS3()
    with patch("s3_store.boto3.client", return_value=fake):
        store = S3SessionStore({"bucket":"sample-bucket", "region":"us-east-2", "access_key_id":"test","secret_access_key":"test"})
    key, created = store.put(parsed,file)
    assert created and key.startswith("sessions/")
    assert fake.puts[0]["IfNoneMatch"] == "*"
    assert fake.puts[0]["ServerSideEncryption"] == "AES256"
    assert fake.puts[0]["Body"] == file
