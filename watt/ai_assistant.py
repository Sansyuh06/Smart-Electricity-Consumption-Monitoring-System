import openai

# Configure OpenAI API
openai.api_key = "YOUR_OPENAI_API_KEY"

def get_ai_response(user_input):
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=user_input,
            max_tokens=150
        )
        return response.choices[0].text.strip()
    except Exception as e:
        return f"AI error: {str(e)}"
