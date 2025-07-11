# test_app.py
def test_service_status(client):
    response = client.get('/status')
    assert b"Service Status Dashboard" in response.data