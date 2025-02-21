import sqlite3
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

#  Step 1: Ensure the fetched_emails table exists
def create_email_table():
    """Create a table to store fetched emails if it does not exist."""
    conn = sqlite3.connect("gmail_info.db")  
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fetched_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            sender TEXT NOT NULL,
            subject TEXT NOT NULL,
            snippet TEXT NOT NULL,
            UNIQUE(email, sender, subject, snippet)  -- Ensures no duplicates
        )
    ''')

    conn.commit()
    conn.close()

def get_user_credentials(email_to_fetch):
    """Fetch credentials for a specific user from the database."""
    conn = sqlite3.connect("gmail_info.db")  
    cursor = conn.cursor()

    cursor.execute("SELECT email, client_id, client_secret, refresh_token FROM gmail_users WHERE email = ?", (email_to_fetch,))
    user = cursor.fetchone()  
    
    conn.close()

    if not user:
        print(f"No credentials found for {email_to_fetch}. Please check the email.")
        return None  

    return user  

def get_gmail_service(client_id, client_secret, refresh_token):
    """Authenticate Gmail API using OAuth credentials from the database."""
    creds = Credentials.from_authorized_user_info({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token"
    })

    return build("gmail", "v1", credentials=creds)  

def fetch_recent_emails(service, max_results=10):
    """Fetch recent emails using Gmail API."""
    try:
        response = service.users().messages().list(userId="me", maxResults=max_results).execute()
        messages = response.get("messages", [])

        if not messages:
            return []

        email_data = []
        for msg in messages:
            msg_id = msg["id"]
            msg_data = service.users().messages().get(userId="me", id=msg_id).execute()

            snippet = msg_data.get("snippet", "")
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
            sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")

            email_data.append((sender, subject, snippet))

        return email_data

    except Exception as e:
        print(f"Error fetching emails: {str(e)}")
        return []

def store_unique_emails(email, emails):
    """Store fetched emails in the database, avoiding duplicates."""
    conn = sqlite3.connect("gmail_info.db")  
    cursor = conn.cursor()

    for sender, subject, snippet in emails:
        try:
            cursor.execute('''
                INSERT INTO fetched_emails (email, sender, subject, snippet) 
                VALUES (?, ?, ?, ?)
            ''', (email, sender, subject, snippet))

        except sqlite3.IntegrityError:
            print(f"Skipping duplicate email: {subject} from {sender}")

    conn.commit()
    conn.close()

def fetch_emails_for_user(email_to_fetch):
    """Fetch emails only for the user specified by input and store unique ones in DB."""
    user = get_user_credentials(email_to_fetch)  

    if not user:
        return  

    email, client_id, client_secret, refresh_token = user
    print(f"\nFetching emails for {email}...")

    try:
        service = get_gmail_service(client_id, client_secret, refresh_token)
        emails = fetch_recent_emails(service)

        if emails:
            print(f"\n{len(emails)} emails fetched for {email}. Storing unique emails...")
            store_unique_emails(email, emails)
            print(f"Unique emails successfully stored in the database.")
        else:
            print("No new emails to store.")

    except Exception as e:
        print(f"Error processing {email}: {str(e)}")

# Ensure table exists
create_email_table()

# User Input: Enter emails to fetch and store unique emails (comma separated)
emails_input = input("Enter the emails of the users you want to fetch emails for (comma separated): ")
emails_list = [email.strip() for email in emails_input.split(",") if email.strip()]

for email in emails_list:
    fetch_emails_for_user(email)


# import sqlite3
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build

# #  Step 1: Ensure the fetched_emails table exists
# def create_email_table():
#     """Create a table to store fetched emails if it does not exist."""
#     conn = sqlite3.connect("gmail_info.db")  
#     cursor = conn.cursor()

#     cursor.execute('''
#         CREATE TABLE IF NOT EXISTS fetched_emails (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             email TEXT NOT NULL,
#             sender TEXT NOT NULL,
#             subject TEXT NOT NULL,
#             snippet TEXT NOT NULL,
#             UNIQUE(email, sender, subject, snippet)  -- Ensures no duplicates
#         )
#     ''')

#     conn.commit()
#     conn.close()

# def get_user_credentials(email_to_fetch):
#     """Fetch credentials for a specific user from the database."""
#     conn = sqlite3.connect("gmail_users.db")  
#     cursor = conn.cursor()

#     cursor.execute("SELECT email, client_id, client_secret, refresh_token FROM gmail_users WHERE email = ?", (email_to_fetch,))
#     user = cursor.fetchone()  
    
#     conn.close()

#     if not user:
#         print(f"No credentials found for {email_to_fetch}. Please check the email.")
#         return None  

#     return user  

# def get_gmail_service(client_id, client_secret, refresh_token):
#     """Authenticate Gmail API using OAuth credentials from the database."""
#     creds = Credentials.from_authorized_user_info({
#         "client_id": client_id,
#         "client_secret": client_secret,
#         "refresh_token": refresh_token,
#         "token_uri": "https://oauth2.googleapis.com/token"
#     })

#     return build("gmail", "v1", credentials=creds)  

# def fetch_recent_emails(service, max_results=10):
#     """Fetch recent emails using Gmail API."""
#     try:
#         response = service.users().messages().list(userId="me", maxResults=max_results).execute()
#         messages = response.get("messages", [])

#         if not messages:
#             return []

#         email_data = []
#         for msg in messages:
#             msg_id = msg["id"]
#             msg_data = service.users().messages().get(userId="me", id=msg_id).execute()

#             snippet = msg_data.get("snippet", "")
#             headers = msg_data.get("payload", {}).get("headers", [])
#             subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
#             sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")

#             email_data.append((sender, subject, snippet))

#         return email_data

#     except Exception as e:
#         print(f"Error fetching emails: {str(e)}")
#         return []

# def store_unique_emails(email, emails):
#     """Store fetched emails in the database, avoiding duplicates."""
#     conn = sqlite3.connect("gmail_info.db")  
#     cursor = conn.cursor()

#     for sender, subject, snippet in emails:
#         try:
#             cursor.execute('''
#                 INSERT INTO fetched_emails (email, sender, subject, snippet) 
#                 VALUES (?, ?, ?, ?)
#             ''', (email, sender, subject, snippet))

#         except sqlite3.IntegrityError:
#             print(f"⚠️ Skipping duplicate email: {subject} from {sender}")

#     conn.commit()
#     conn.close()

# def fetch_emails_for_user(email_to_fetch):
#     """Fetch emails only for the user specified by input and store unique ones in DB."""
#     user = get_user_credentials(email_to_fetch)  

#     if not user:
#         return  

#     email, client_id, client_secret, refresh_token = user
#     print(f"\nFetching emails for {email}...")

#     try:
#         service = get_gmail_service(client_id, client_secret, refresh_token)
#         emails = fetch_recent_emails(service)

#         if emails:
#             print(f"\n{len(emails)} emails fetched for {email}. Storing unique emails...")
#             store_unique_emails(email, emails)
#             print(f"Unique emails successfully stored in the database.")
#         else:
#             print("No new emails to store.")

#     except Exception as e:
#         print(f"Error processing {email}: {str(e)}")

# #  Ensure table exists
# create_email_table()

# #  User Input: Enter email to fetch and store unique emails
# email_to_fetch = input("Enter the email of the user you want to fetch emails for: ")
# fetch_emails_for_user(email_to_fetch)
