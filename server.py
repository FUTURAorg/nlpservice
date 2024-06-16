from concurrent import futures
import os
from typing import List
import grpc

from langchain_openai import ChatOpenAI
from model import Conversation

from futuracommon.protos import nlp_pb2, nlp_pb2_grpc
from futuracommon.protos import tts_pb2, tts_pb2_grpc
from futuracommon.protos import healthcheck_pb2, healthcheck_pb2_grpc

from futuracommon.SessionManager import RedisSessionManager

import logging 
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger('NLPService')

rd = RedisSessionManager(os.environ.get("REDIS_HOST", "session_manager"), 6379, 0)

chat = ChatOpenAI(
        model="gpt-3.5-turbo-0125",
        openai_api_key=os.environ.get('OPEN_AI_KEY'),
    )

# chat = Ollama(model="bambucha/saiga-llama3")

conversations: dict[str, Conversation] = {}
is_gpt = True

class NLPService(nlp_pb2_grpc.NLPServiceServicer):
    
    def __init__(self) -> None:
        super().__init__()
        self.last_generated = ""
        self.channel_synt = grpc.insecure_channel(f'{os.environ.get("SYNT_SERVICE_HOST", "syntservice:50050")}')
        self.stub_synt = tts_pb2_grpc.TextToSpeechStub(channel=self.channel_synt)
    
    def NotifySuccess(self, request, context):
        
        client_data: dict = rd.get_all(client_id=request.client_id)
        logger.info(f"got {client_data.get('q', '')} {client_data.get('identity', '')} for client {request.client_id}")
        
        identity = client_data.get('identity', None)
        
        if not request.client_id in conversations:
            conv = Conversation(model=chat, is_gpt=is_gpt)
            conversations[request.client_id] = conv
            
            conv.add_user_message("Привет!")
            logger.info("Using new conv")
            
        else:
            conv = conversations[request.client_id]
            logger.info(f"Using old conv")
            
            if conv.human_name != identity:
                conv = Conversation(model=chat, is_gpt=is_gpt)
                conversations[request.client_id] = conv
                conv.add_user_message("Привет!")
                logger.info("Re-created conv")
                
        
        conv.set_result_of_recognition(identity, recognized=True if identity else False)
            
        question = client_data.get('q', None)
        
        if not question:
            logger.info("No question found in SessionManager")
            return nlp_pb2.NotificationResponse(acknowledged=True)
        
        if not conv.check_question_complite(question):
            logger.info("Question is not complete. Abort answer generation")
            return nlp_pb2.NotificationResponse(acknowledged=True)
        
        conv.add_user_message(question)
        
        generated = conv.generate_message()
        
        if conv.human_name:
            
            rd.save(cliend_id=request.client_id, key="identity", value=conv.human_name)
        
        
        if self.last_generated != generated:
            self.stub_synt.ProcessText(tts_pb2.TextRequest(text=generated, session_id=request.client_id))
        
        logger.info(f"{conv.state} {generated}")
        # logger.info(f"{conv.log[-5:]}")
        
        return nlp_pb2.NotificationResponse(acknowledged=True)

class HealthServicer(healthcheck_pb2_grpc.HealthServiceServicer):
    def Check(self, request, context):
        
        return healthcheck_pb2.HealthResponse(status=1, current_backend="GPT")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    nlp_pb2_grpc.add_NLPServiceServicer_to_server(NLPService(), server)
    healthcheck_pb2_grpc.add_HealthServiceServicer_to_server(HealthServicer(), server)
    
    server.add_insecure_port('[::]:50050')
    server.start()
    logger.info("Listening...")
    server.wait_for_termination()
    


if __name__ == "__main__":
    serve()