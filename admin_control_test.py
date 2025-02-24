import base64
import json
import os

from flask import Flask, request, render_template_string, redirect, url_for, session
from google.oauth2 import service_account
from googleapiclient.discovery import build
import redis

# For embeddings and FAISS
import faiss
from sentence_transformers import SentenceTransformer
import numpy as np

# For LLM generation (example using OpenAI)
import openai
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
app.secret_key = "234"  # Required for session management

# Redis client (make sure Redis server is running locally or adjust host/port accordingly)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Gmail API credentials and scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
SERVICE_ACCOUNT_FILE = r"C:\Users\OMEN\Downloads\admin-test-451812-73c7f4a80797.json"

# OpenAI API key (set your key as an environment variable or replace below)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Sentence Transformer model for embeddings
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_gmail_service(user_email):
    """Build and return a Gmail service object authorized as user_email."""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=SCOPES
    )
    delegated_credentials = credentials.with_subject(user_email)
    service = build('gmail', 'v1', credentials=delegated_credentials)
    return service

def get_message_body(payload):
    """Recursively extract the plain text body from the payload."""
    body = ""
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('parts'):
                body += get_message_body(part)
            elif part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
                data = part['body']['data']
                body += base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='replace')
    elif payload.get('mimeType') == 'text/plain' and payload.get('body', {}).get('data'):
        data = payload['body']['data']
        body += base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='replace')
    return body

def list_user_messages_for_multiple_users(user_emails, max_results=10):
    """
    Fetch messages for each user in user_emails and store them in Redis.
    Returns a dictionary keyed by user email with message details.
    """
    results = {}

    for user_email in user_emails:
        print(f"Fetching messages for: {user_email}")
        service = get_gmail_service(user_email)

        response = service.users().messages().list(
            userId='me',
            maxResults=max_results
        ).execute()
        messages = response.get('messages', [])

        if not messages:
            print(f"No messages found for {user_email}.\n")
            results[user_email] = []
            continue

        detailed_messages = []
        for msg in messages:
            msg_detail = service.users().messages().get(
                userId='me',
                id=msg['id'],
                format='full'
            ).execute()

            snippet = msg_detail.get('snippet', '')
            payload = msg_detail.get('payload', {})
            headers = payload.get('headers', [])

            subject = None
            from_email = None
            for header in headers:
                if header['name'].lower() == 'subject':
                    subject = header['value']
                elif header['name'].lower() == 'from':
                    from_email = header['value']

            # Extract the full plain text body
            body = get_message_body(payload)

            detailed_messages.append({
                'id': msg['id'],
                'snippet': snippet,
                'subject': subject,
                'from': from_email,
                'body': body
            })

        # Store fetched emails in Redis under a key like "emails:user@example.com"
        redis_key = f"emails:{user_email}"
        redis_client.set(redis_key, json.dumps(detailed_messages))

        results[user_email] = detailed_messages
        print(f"Found {len(detailed_messages)} messages for {user_email}.\n")

    return results


def build_faiss_index(user_email):
    """
    Retrieves stored emails from Redis for a given user, builds a FAISS index,
    and returns both the index and a list of email messages.
    """
    redis_key = f"emails:{user_email}"
    emails_json = redis_client.get(redis_key)
    if not emails_json:
        return None, [], []
    messages = json.loads(emails_json)
    
    # Use a combination of subject, snippet, and body for embeddings
    docs = [
        f"Subject: {msg.get('subject', '')}\nSnippet: {msg.get('snippet', '')}\nBody: {msg.get('body', '')}"
        for msg in messages
    ]
    
    if not docs:
        return None, messages, []
    
    embeddings = embedding_model.encode(docs, convert_to_numpy=True)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(embeddings)
    return index, messages, docs

def query_emails_with_rag(user_email, query, top_k=3):
    """
    Given a user email and a query, builds a FAISS index from stored emails,
    retrieves the top_k relevant documents, and returns them.
    """
    index, messages, docs = build_faiss_index(user_email)
    if index is None:
        return "No emails available for this user."

    # Compute query embedding
    query_vec = embedding_model.encode([query], convert_to_numpy=True)
    distances, indices = index.search(query_vec, top_k)
    
    # Retrieve the corresponding documents
    retrieved_docs = [docs[i] for i in indices[0] if i < len(docs)]
    
    # Create a prompt with retrieved context for the LLM
    prompt = "Answer the following question based on the context from emails:\n\n"
    prompt += "Context:\n" + "\n---\n".join(retrieved_docs) + "\n\n"
    prompt += "Question: " + query + "\nAnswer:"
    
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an assistant that answers questions based on provided email context."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=150
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        answer = f"Error generating response: {e}"
    
    return answer

@app.route('/')
def index():
    """Home page: Form to fetch emails."""
    return '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Gmail Messages Fetch Demo</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css">
</head>
<body class="bg-light">
  <div class="container py-5">
    <h1 class="mb-4 text-center animate__animated animate__fadeInDown">Gmail Messages Fetch Demo</h1>
    <div class="row justify-content-center">
      <div class="col-md-8 col-lg-6">
        <div class="card shadow animate__animated animate__fadeInUp">
          <div class="card-body">
            <form method="POST" action="/fetch">
              <div class="mb-3">
                <label for="user_emails" class="form-label">User Emails (comma-separated):</label>
                <input type="text" class="form-control" id="user_emails" name="user_emails"
                       placeholder="user1@domain.com, user2@domain.com" required>
              </div>
              <div class="mb-3">
                <label for="max_results" class="form-label">Max Results:</label>
                <input type="number" class="form-control" id="max_results" name="max_results" value="10" min="1" />
              </div>
              <button type="submit" class="btn btn-primary w-100">Fetch Emails</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
    '''

@app.route('/fetch', methods=['POST'])
def fetch():
    """Handles the email fetching form submission."""
    user_emails_str = request.form.get('user_emails', '')
    max_results_str = request.form.get('max_results', '10')

    user_emails = [email.strip() for email in user_emails_str.split(',') if email.strip()]
    max_results = int(max_results_str) if max_results_str.isdigit() else 10

    messages_dict = list_user_messages_for_multiple_users(user_emails, max_results)

    # Save the fetched user emails in session so the dashboard can use them
    session['user_emails'] = user_emails

    # Optionally, store the fetched messages dictionary in session if needed

    return redirect(url_for('dashboard'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    """Dashboard page that displays fetched emails and a sidebar chatbot."""
    # Retrieve the list of fetched emails from session.
    fetched_emails = session.get('user_emails', [])
    chat_response = ""
    selected_email = None

    # Process chat query if submitted.
    if request.method == 'POST' and request.form.get('query'):
        selected_email = request.form.get('user_email')
        query = request.form.get('query', '')
        if query and selected_email:
            chat_response = query_emails_with_rag(selected_email, query)

    # Build dropdown options for email selection.
    email_options = ""
    for email in fetched_emails:
        selected_attr = "selected" if email == selected_email else ""
        email_options += f'<option value="{email}" {selected_attr}>{email}</option>'

    # Build the emails content (compact version)
    emails_html = ""
    for email in fetched_emails:
        # Retrieve emails for each user from Redis
        redis_key = f"emails:{email}"
        emails_json = redis_client.get(redis_key)
        messages = json.loads(emails_json) if emails_json else []
        emails_html += f'<h4 class="mt-3">{email}</h4>'
        if not messages:
            emails_html += '<div class="alert alert-info">No messages found.</div>'
        else:
            for msg in messages:
                emails_html += f'''
                <div class="card mb-2">
                  <div class="card-body p-2">
                    <h6 class="card-title mb-1">Subject: {msg.get('subject', '')}</h6>
                    <p class="card-text mb-0"><small>From: {msg.get('from', '')}</small></p>
                    <p class="card-text"><small>{msg.get('snippet', '')}</small></p>
                  </div>
                </div>
                '''

    # Render a two-column layout with Bootstrap:
    # Left column: Fetched emails, Right column: Chat panel.
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Dashboard - Emails & Chat</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body { background-color: #f8f9fa; }
    .emails-panel { overflow-y: auto; max-height: 80vh; }
    .chat-panel { background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }
    .chat-response { white-space: pre-wrap; background: #f1f1f1; padding: 10px; border-radius: 5px; }
  </style>
</head>
<body>
  <div class="container-fluid mt-3">
    <div class="row">
      <!-- Emails Panel -->
      <div class="col-md-8 emails-panel">
        <h2>Fetched Emails</h2>
        {{ emails_html|safe }}
        <div class="mt-4">
          <a href="/" class="btn btn-secondary">Back Home</a>
        </div>
      </div>
      <!-- Chat Panel -->
      <div class="col-md-4">
        <div class="chat-panel">
          <h4>Chat with Email Context</h4>
          <form method="POST">
            <div class="mb-3">
              <label for="user_email" class="form-label">Select Email:</label>
              <select class="form-select" id="user_email" name="user_email" required>
                {{ email_options|safe }}
              </select>
            </div>
            <div class="mb-3">
              <label for="query" class="form-label">Ask a question:</label>
              <input type="text" class="form-control" id="query" name="query" placeholder="e.g., When is my interview?" required>
            </div>
            <button type="submit" class="btn btn-primary w-100">Send</button>
          </form>
          {% if chat_response %}
          <div class="mt-3">
            <h6>Response:</h6>
            <div class="chat-response">{{ chat_response }}</div>
          </div>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
    ''', emails_html=emails_html, email_options=email_options, chat_response=chat_response)

if __name__ == '__main__':
    app.run(debug=True)
