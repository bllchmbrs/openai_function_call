import openai
import enum
import asyncio

from pydantic import Field
from typing import List, Tuple
from openai_function_call import OpenAISchema
from tenacity import retry, stop_after_attempt


class QueryType(str, enum.Enum):
    """
    Enumeration representing the types of queries that can be asked to a question answer system.
    """

    # When i call it anything beyond 'merge multiple responses' the accuracy drops significantly.
    SINGLE_QUESTION = "SINGLE"
    MERGE_MULTIPLE_RESPONSES = "MERGE_MULTIPLE_RESPONSES"


class QueryAnswer(OpenAISchema):
    question: str
    answer: str


class Query(OpenAISchema):
    """
    Class representing a single question in a question answer subquery.
    Can be either a single question or a multi question merge.
    """

    id: int = Field(..., description="Unique id of the query")
    question: str = Field(
        ...,
        description="Question we are asking using a question answer system, if we are asking multiple questions, this question is asked by also providing the answers to the sub questions",
    )
    dependancies: List[int] = Field(
        default_factory=list,
        description="List of sub questions that need to be answered before we can ask the question. Use a subquery when anything may be unknown, and we need to ask multiple questions to get the answer. Dependences must only be other queries.",
    )
    node_type: QueryType = Field(
        default=QueryType.SINGLE_QUESTION,
        description="Type of question we are asking, either a single question or a multi question merge when there are multiple questions",
    )
    original_question: bool = Field(
        default=False,
        description="the root question is the original question we are asking",
    )


class QueryPlan(OpenAISchema):
    """
    Container class representing a tree of questions to ask a question answer system.
    and its dependencies. Make sure every question is in the tree, and every question is asked only once.
    """

    query_graph: List[Query] = Field(
        ..., description="The original question we are asking"
    )


Query.update_forward_refs()
QueryPlan.update_forward_refs()


def query_planner(question: str) -> QueryPlan:
    PLANNING_MODEL = "gpt-4"
    ANSWERING_MODEL = "gpt-3.5-turbo-0613"

    messages = [
        {
            "role": "system",
            "content": "You are a world class query planning algorithm capable of breaking apart questions into its depenencies queries such that the answers can be used to inform the parent question. Do not answer the questions, simply provide correct compute graph with good specific questions to ask and relevant dependencies. Before you call the function, think step by step to get a better understanding the problem.",
        },
        {
            "role": "user",
            "content": f"Consider: {question}\n Before you call the function, think step by step to get a correct query plan.",
        },
        {
            "role": "assistant",
            "content": "Lets think step by step to find the correct query plan that does not make any assuptions of what is known.",
        },
    ]

    completion = openai.ChatCompletion.create(
        model=PLANNING_MODEL,
        temperature=0,
        messages=messages,
        max_tokens=1000,
    )

    messages.append(completion.choices[0].message)

    messages.append(
        {
            "role": "user",
            "content": "Using that information produce the complete and correct query plan.",
        }
    )

    completion = openai.ChatCompletion.create(
        model=ANSWERING_MODEL,
        temperature=0,
        functions=[QueryPlan.openai_schema],
        function_call={"name": QueryPlan.openai_schema["name"]},
        messages=messages,
        max_tokens=1000,
    )
    root = QueryPlan.from_response(completion)
    return root


if __name__ == "__main__":
    from pprint import pprint

    plan = query_planner(
        "What is the difference in populations of Canada and the Jason's home country?"
    )
    pprint(plan.dict())
    """
    {'query_graph': [{'dependancies': [],
                    'id': 1,
                    'node_type': <QueryType.SINGLE_QUESTION: 'SINGLE'>,
                    'question': "Identify Jason's home country"},
                    {'dependancies': [],
                    'id': 2,
                    'node_type': <QueryType.SINGLE_QUESTION: 'SINGLE'>,
                    'question': 'Find the population of Canada'},
                    {'dependancies': [1],
                    'id': 3,
                    'node_type': <QueryType.SINGLE_QUESTION: 'SINGLE'>,
                    'question': "Find the population of Jason's home country"},
                    {'dependancies': [2, 3],
                    'id': 4,
                    'node_type': <QueryType.SINGLE_QUESTION: 'SINGLE'>,
                    'question': 'Calculate the difference in populations between '
                                "Canada and Jason's home country"}]}    
    """