import json
import logging
from typing import Dict, List, Any, Optional

from redis import Redis
from redis.exceptions import RedisError

from config.settings import DEFAULT_CONFIG
from just_os.database import get_redis_client

logger = logging.getLogger(__name__)

class ChatManager:
    """
    Manages chat history using Redis as a storage backend.
    Provides methods to add messages and retrieve conversation history.
    """
    
    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize the ChatManager with a Redis client.
        
        Args:
            redis_client: Optional Redis client instance. If None, uses the default client.
        """
        self.redis = redis_client or get_redis_client()
        self.message_ttl = DEFAULT_CONFIG["MESSAGE_TTL"]
        # the newest messages kept per chat (a question and its answer are two); 0 = all
        self.max_messages = DEFAULT_CONFIG.get("MAX_HISTORY_MESSAGES", 20)
        logger.debug("ChatManager initialized")

    def add_message(self, chat_id: str, message: Dict[str, Any]) -> bool:
        """
        Add a message to the chat history.
        
        Args:
            chat_id: Unique identifier for the chat session
            message: Message data to store
            
        Returns:
            bool: True if message was added successfully, False otherwise
        """
        key = f"chat:{chat_id}"
        
        try:
            # One transaction: add the message (the list is newest first), keep the newest
            # MAX_HISTORY_MESSAGES, reset the TTL. A chat can never grow without bound.
            pipe = self.redis.pipeline(transaction=True)
            pipe.lpush(key, json.dumps(message))
            if self.max_messages > 0:
                pipe.ltrim(key, 0, self.max_messages - 1)
            pipe.expire(key, self.message_ttl)
            pipe.execute()
            logger.debug(f"Added message to chat {chat_id}")
            return True
        except RedisError as e:
            logger.error(f"Failed to add message to chat {chat_id}: {str(e)}")
            return False

    def get_history(self, chat_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve the chat history for a given chat ID.
        
        Args:
            chat_id: Unique identifier for the chat session
            
        Returns:
            List of messages in chronological order (oldest first)
        """
        key = f"chat:{chat_id}"
        try:
            messages = self.redis.lrange(key, 0, -1)
            # Reverse to get chronological order (oldest first)
            return [json.loads(msg) for msg in messages][::-1]
        except RedisError as e:
            logger.error(f"Failed to retrieve history for chat {chat_id}: {str(e)}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode message in chat {chat_id}: {str(e)}")
            return []
