"""
API endpoint tests using Django test client.
LLM is mocked — no real Groq API call needed.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from conversations.models import Conversation, Message


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass123")


@pytest.fixture
def auth_client(client, user):
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def mock_llm():
    """Mock ChatService so no real LLM call is made in any test."""
    with patch("conversations.views._chat_service") as mock:
        def fake_handle(conversation, content):
            msg = Message(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content="Mocked LLM reply.",
                tokens_used=20,
            )
            msg.save()
            return msg
        mock.handle_message.side_effect = fake_handle
        yield mock


# ── Auth ─────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRegister:
    def test_register_returns_token(self, client):
        r = client.post("/api/auth/register/", {
            "username": "newuser",
            "email": "new@test.com",
            "password": "securepass1",
        }, format="json")
        assert r.status_code == 201
        assert "token" in r.data
        assert r.data["user"]["username"] == "newuser"

    def test_duplicate_username_returns_400(self, client, user):
        r = client.post("/api/auth/register/", {
            "username": "testuser",   # already exists
            "password": "securepass1",
        }, format="json")
        assert r.status_code == 400

    def test_unauthenticated_request_returns_401(self, client):
        r = client.get("/api/conversations/")
        assert r.status_code == 401


# ── Conversations ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestConversations:
    def test_create_conversation(self, auth_client, mock_llm):
        r = auth_client.post("/api/conversations/", {
            "first_message": "Hello!",
            "mode": "open",
        }, format="json")
        assert r.status_code == 201
        assert r.data["mode"] == "open"
        assert "messages" in r.data

    def test_list_conversations(self, auth_client, mock_llm):
        auth_client.post("/api/conversations/", {"first_message": "Hi", "mode": "open"}, format="json")
        r = auth_client.get("/api/conversations/")
        assert r.status_code == 200
        assert r.data["count"] >= 1

    def test_retrieve_conversation_has_messages(self, auth_client, mock_llm):
        create = auth_client.post("/api/conversations/", {"first_message": "Hi", "mode": "open"}, format="json")
        conv_id = create.data["id"]
        r = auth_client.get(f"/api/conversations/{conv_id}/")
        assert r.status_code == 200
        assert len(r.data["messages"]) >= 1

    def test_delete_conversation(self, auth_client, mock_llm):
        create = auth_client.post("/api/conversations/", {"first_message": "Hi", "mode": "open"}, format="json")
        conv_id = create.data["id"]
        r = auth_client.delete(f"/api/conversations/{conv_id}/")
        assert r.status_code == 204
        assert not Conversation.objects.filter(id=conv_id).exists()

    def test_send_message_returns_assistant_reply(self, auth_client, mock_llm):
        create = auth_client.post("/api/conversations/", {"first_message": "Hi", "mode": "open"}, format="json")
        conv_id = create.data["id"]
        r = auth_client.post(f"/api/conversations/{conv_id}/messages/", {
            "content": "Tell me more."
        }, format="json")
        assert r.status_code == 200
        assert r.data["role"] == "assistant"
        assert r.data["content"] == "Mocked LLM reply."

    def test_cannot_access_other_users_conversation(self, auth_client, mock_llm, db):
        create = auth_client.post("/api/conversations/", {"first_message": "Private", "mode": "open"}, format="json")
        conv_id = create.data["id"]

        # Login as different user
        user2   = User.objects.create_user(username="user2", password="pass12345")
        token2, _ = Token.objects.get_or_create(user=user2)
        other_client = APIClient()
        other_client.credentials(HTTP_AUTHORIZATION=f"Token {token2.key}")

        r = other_client.get(f"/api/conversations/{conv_id}/")
        assert r.status_code == 404  # not 403 — avoids info leak
