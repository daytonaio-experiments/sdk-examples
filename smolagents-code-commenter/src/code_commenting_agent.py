import os
import openai

class CodeCommenter:
    def __init__(self):
        # Get API key from environment variable
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.client = openai.OpenAI(api_key=self.api_key)

    def analyze_code(self, code: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a code analysis assistant."},
                    {"role": "user", "content": f"Analyze this Python code:\n\n{code}"}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Analysis failed: {str(e)}"

def comment_on_code(code: str) -> str:
    """
    This function takes Python code, uses SmolAgent to generate comments on the code,
    and returns the commented code.
    """
    commenter = CodeCommenter()
    commented_code = commenter.analyze_code(code)
    return commented_code

if __name__ == "__main__":
    # Example Python code (you can replace this with any code)
    user_code = """
def greet(name):
    print(f'Hello, {name}!')
greet('World')
"""

    # Comment the code using SmolAgent
    commented_code = comment_on_code(user_code)

    # Output the commented code
    print("Commented Code:\n")
    print(commented_code)
