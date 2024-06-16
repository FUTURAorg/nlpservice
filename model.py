from langchain_openai import ChatOpenAI
from langchain.llms.fake import FakeListLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain.output_parsers.boolean import BooleanOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.exceptions import OutputParserException
import datetime
from datetime import timedelta
from fa_api import FaAPI
from itertools import groupby
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage


def get_time_table(teacher_name, start: datetime.datetime, end: datetime.datetime):
    fa = FaAPI()
    try:
        teacher_id = fa.search_teacher(teacher_name)[0]["id"]
        return fa.timetable_teacher(teacher_id, start.strftime('%Y.%m.%d'), end.strftime('%Y.%m.%d'))     
    except Exception as e:
        print(e)
        return []
    
    
def get_teacher_name(search_name):
    fa = FaAPI()
    res = fa.search_teacher(search_name)
    if res:
        res = list(map(lambda x: x["label"], res))[:5]
    return res


def get_day_of_week(day_number):
    days_of_week_russian = {
        1: 'Пн',
        2: 'Вт',
        3: 'Ср',
        4: 'Чт',
        5: 'Пт',
        6: 'Сб',
        7: 'Вс'
    }
    return days_of_week_russian.get(day_number, 'Invalid day')


def get_weekday_number(weekday):
    days_of_week_russian = {
        1: "Пн",
        2: "Вт",
        3: "Ср",
        4: "Чт",
        5: "Пт",
        6: "Сб",
        7: "Вс",
    }
    lowercase_weekday_mapping = {v.lower(): k for k, v in days_of_week_russian.items()}
    return lowercase_weekday_mapping.get(weekday.strip().lower(), "Invalid day")


def get_schedule_period(schedule_info):
    today = datetime.datetime.today()
    if schedule_info.get("week", False):
        # If week is requested
        if schedule_info.get("currentWeek", False):
            # If current week is requested
            start_date = today - datetime.timedelta(days=today.weekday())
            end_date = start_date + datetime.timedelta(days=6)
        elif schedule_info.get("nextWeek", False):
            # If next week is requested
            start_date = (
                today
                - datetime.timedelta(days=today.weekday())
                + datetime.timedelta(weeks=1)
            )
            end_date = start_date + datetime.timedelta(days=6)
        else:
            print("Defaulting to current week")
            start_date = today - datetime.timedelta(days=today.weekday())
            end_date = start_date + datetime.timedelta(days=6)
    elif schedule_info.get("day", False):
        input_date = None
        if schedule_info.get("date", None):
            date = "".join(l for l in schedule_info["date"] if l in "0123456789.")
            input_date = datetime.datetime.strptime(date, "%d.%m").replace(year=2024)
        if input_date < today or input_date is None:
            print("l")
            if schedule_info.get("dayOfWeek", None):
                today_weekday = today.weekday()
                weekday = get_weekday_number(schedule_info["dayOfWeek"]) - 1
                print(today_weekday, weekday)
                if schedule_info.get("currentWeek", None) and today_weekday <= weekday:
                    input_date = today + timedelta(days=weekday - today_weekday)
                else:

                    days_until_next_week = 7 - today_weekday
                    start_of_next_week = today + timedelta(days=days_until_next_week)
                    print(start_of_next_week)
                    print(weekday)
                    input_date = start_of_next_week + timedelta(days=weekday)

        start_date = input_date
        end_date = input_date
    else:
        # Invalid request, return None
        return None

    # Format and return the start and end dates
    return (start_date, end_date)


def generate_timetable_unit_description(timetable_unit):
    description = ""
    description += f"{timetable_unit['kindOfWork']}\n"
    description += f"Предмет{timetable_unit['discipline']}\n"

    if timetable_unit["listGroups"]:
        description += f"Группа/ы: {', '.join(map(lambda x: x['group'], timetable_unit['listGroups']))}\n"
    else:
        description += f"Поток: {timetable_unit['stream']}\n"
    description += f"{timetable_unit['auditorium']} / {timetable_unit['building']}\n"

    description += (
        f"Время: {timetable_unit['beginLesson']} - {timetable_unit['endLesson']}\n"
    )

    # description +=

    return description


def generate_timetable_description(timetable):
    res = []

    for key, elements in groupby(timetable, key=lambda x: x["date"]):
        elements = list(elements)
        text = ""

        timetable_unit = elements[0]
        date_obj = datetime.datetime.strptime(timetable_unit["date"], "%Y.%m.%d")
        formatted_date = date_obj.strftime("%d.%m.%Y")
        text += (
            f"Дата: {formatted_date}, {get_day_of_week(timetable_unit['dayOfWeek'])}"
        )
        text += "\n"
        text += "\n".join(map(generate_timetable_unit_description, elements))
        res.append(text)
    return "---------".join(res)


PROMPT_CHECK_NAME = """Using previus chat history tell that is users name, and did you get confirmation what it is full users name. Answer with JSON with schema
{"fullname": str, - surname name or middlename
"got_confirmation": bool - true/false}"""

PROMPT_PARSE_QUESTION = """Today is {day_of_week} {date}
Extract from the user's response information about the date for which he wants to know the schedule
User question: '{question}'
Output the answer in JSON format with the following fields:
'day': bool, True, if information is requested for single day,
'week': bool, True, if information is requested for whole week, day or week should be True
'nextWeek' - bool,
'currentWeek' - bool,
'dayOfWeek' - str, 'пн'/'вт'/'ср'/'чт'/'пт'/'сб',
'date' - the date (dd.mm) for which the user wants to know the schedule (equal or more than todays date)

Examples:
Question: 'Какие занятия во вторник?'
'{{\n "day": true,\n "dayOfWeek": "вт",\n "currentWeek": true,\n, \n "date": "10.01"}}'

"Question: 'Сколько занятий на следующей неделе?'
'{{\n "week": true,\n "nextWeek": true\n}}'
"""

PROMPT_CHECK_FOR_TIMETABLE = """Does this question requires information about schedule?\nQuestion:"{question}"\nAnswer ONLY "YES" or "NO" """
PROMPT_CHECK_FOR_NAME_AGREE = """If you asked for user's name and user confirmed their name, then answer "YES" else answer "NO"\n"""
PROMPT_CHECK_FOR_NAME_SAID = """Using information about conversatiom check, if user said their name, then answer "ДА" else answer "НЕТ"\n"""
PROMPT_CHECK_IF_COMPLITE = """Is user message or question complete or not, is he going to say something more? Do not consider punctuation signs. Use info from previous messages
Examples
Message: "Да" Answer: "YES"
Message: "Нет" Answer: "YES"
Message: "Какие у меня сегодня" Answer: "NO"
Message: "Да, поэтому скажи" Answer: "NO"
Message: "Во сколько начало занятий" Answer: "YES"
Message: "Есть ли в среду занятия по Математике" Answer: "YES"
Message: "Какие занятия в среду" Answer: "YES"
Message: "Как дела" Answer: "YES"
Message: "Имя Фамилия" Answer: "YES"
Message: "Фамилия Имя" Answer: "YES"
Message: "Фамилия Имя Отчество" Answer: "YES"
Message: "Привет" Answer: "YES"

Message: {text} Answer ONLY "YES" or "NO" """


class Conversation:
    state_dict = {
        1: "Ожидание результата распознавания",
        2: "Запрашивание имени",
        3: "Отвечание на вопросы",
    }

    def __init__(self, model, is_gpt=False):
        self.model = model
        self.state = 1
        self.history = [
            SystemMessage(
                content="You are a voice assistant who checks persons schedule and use information to respectfully answer the questions. Speak ONLY russian language."
            )
        ]
        self.human_name = None
        self.log = []
        self.is_gpt = is_gpt

    def set_result_of_recognition(self, human_name, recognized):
        if recognized:
            self.human_name = human_name
            self.set_state(3)
        else:
            message = SystemMessage(f"You should ask for user's name")
            self.history.append(message)
            self.log.append(message)
            self.set_state(2)

    def check_for_name(self):
        parser = JsonOutputParser()
        messages = self.history + [HumanMessage(content=PROMPT_CHECK_NAME)]
        chain = self.model | parser
        try:
            res_json = chain.invoke(messages)

        except OutputParserException as e:
            print(e)
            return {"got_confirmation": False}
        self.log.append(res_json)
        return res_json

    def set_state(self, state):

        self.state = state

    def add_user_message(self, content):
        if self.state == 1:
            print("Ожидается результат распознавания")
            return None
        self.history.append(HumanMessage(content=content))
        self.log.append(HumanMessage(content=content))

    def check_for_timetable(self):
        message = self.history[-1]
        parser = BooleanOutputParser()
        prompt = PromptTemplate(
            template=PROMPT_CHECK_FOR_TIMETABLE, input_variables=["question"]
        )
        chain = prompt | self.model | parser
        try:
            timetable_needed = chain.invoke({"question": message.content})
        except OutputParserException:
            return False
        self.log.append(timetable_needed)
        return timetable_needed

    def check_for_name_agreement(self):
        parser = BooleanOutputParser()

        prompt = SystemMessage(PROMPT_CHECK_FOR_NAME_AGREE)
        chain = self.model | parser
        
        try:
            is_name = chain.invoke(self.history + [prompt])
        except ValueError:
            return False
        
        return is_name
    
    def check_name_said(self):
        parser = BooleanOutputParser(true_val="ДА", false_val="НЕТ")

        prompt = SystemMessage(PROMPT_CHECK_FOR_NAME_SAID)
        chain = self.model | parser
        
        try:
            is_name = chain.invoke(self.history + [prompt])
        except ValueError:
            return False
        
        return is_name
           
    # @traceable
    def parse_question(self):
        parser = JsonOutputParser()
        today = datetime.datetime.today()
        date = today.strftime("%d.%m.%Y (дд.мм.гггг)")
        day_of_week = get_day_of_week(today.weekday() + 1)
        prompt = PROMPT_PARSE_QUESTION.format(
            day_of_week=day_of_week, date=date, question=self.history[-1].content
        )
        chain = self.model | parser
        try:
            res_json = chain.invoke(prompt)
            self.log.append(res_json)
        except OutputParserException as e:
            print(e)
            return {"date": today.strftime("%d.%m"), "day": True}

        return res_json

    # @traceable
    def generate_message(self):
        messages = self.history
        message = None
        if self.state == 2:
            name_said = self.check_name_said() if len(self.history) > 2 else False
            
            dct = {
                "fullname": "",
                "got_confirmation": False
            }
            
            if name_said:
                dct = self.check_for_name()
                self.human_name = dct["fullname"]
                
            if dct["got_confirmation"] and self.human_name:
                self.human_name = dct["fullname"]
                self.set_state(3)
                response = self.model.invoke(self.history)
            elif self.human_name and not dct["got_confirmation"]:
                if self.check_for_name_agreement():
                    dct["got_confirmation"] = True
                    self.set_state(3)
                else:
                    message = SystemMessage(f"Подтверди, что {self.human_name} - это имя пользователя")
                    messages = self.history + [message]
            else:
                message = SystemMessage(f"Ask for users full name")
                messages = self.history + [message]
                
            response = self.model.invoke(messages)
            
            if message:
                self.log.append(message)
            self.log.append(response)
            
        elif self.state == 3:
            if self.check_for_timetable():
                parsed_question = self.parse_question()
                period = get_schedule_period(parsed_question)
                if period:
                    # timetable = time_table
                    timetable = get_time_table(
                        self.human_name, start=period[0], end=period[1]
                    )
                else:
                    print("Default to today")
                    timetable = get_time_table(self.human_name, datetime.datetime.today(), datetime.datetime.today())
                # timetable = time_table
                
                timetable_as_text = generate_timetable_description(timetable)
                prompt = f"Schedule: {timetable_as_text}\n---------\nUsing info from schedule answer question, as briefly as possible, only necessary information, write like you speak, write numbers with words. This schedule cannot be changed. Обращайся на вы"
                messages = self.history + [HumanMessage(prompt)]
                self.log.append(HumanMessage(prompt))
                response = self.model.invoke(messages)
                self.log.append(response)
            else:
                response = self.model.invoke(self.history)
                self.log.append(response)

        else:
            response = self.model.invoke(self.history)
            self.log.append(response)

        self.history.append(response)
        
        
        return response.content if self.is_gpt else response

    def check_question_complite(self, text):
        parser = BooleanOutputParser(true_val="YES", false_val="NO")
        prompt = HumanMessage(PROMPT_CHECK_IF_COMPLITE.format(text=text))
        chain = self.model | parser
        try:
            is_complete = chain.invoke([prompt])
        except ValueError as e:
            return False
        return is_complete


if __name__ == "__main__":
    # chat = ChatOpenAI(
    #     model="gpt-3.5-turbo-0125",
    #     openai_api_key="****",
    # )
    
    # from langchain_community.llms import Ollama

    # chat = Ollama(model="bambucha/saiga-llama3")
    
    conv = Conversation(model=chat)
    conv.add_user_message("Привет!")
    conv.set_result_of_recognition("", recognized=False)
    print(conv.generate_message())
    while True:
        user_msg = input(f'{conv.state} > ')
        print(conv.log)
        conv.add_user_message(user_msg)
        print(conv.generate_message())
