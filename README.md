# Google Cloud Console Setup

1. Create a Project: Go to the [Google Cloud Console](https://console.cloud.google.com/) and create a new project.
2. Enable APIs: Navigate to APIs & Services > Library using the left sidebar menu.
3. Search for the Google Sheets API and click Enable.
4. Return to the Library, search for the Google Drive API, and click Enable.
5. Create a Service Account: Go to APIs & Services > Credentials.
6. Click Create Credentials at the top and select Service Account.
7. Provide a name for the service account and click Create and Continue, then click Done.
8. Generate the Key: Under the "Service Accounts" list, click the email address of the account you just created.
9. Navigate to the Keys tab.
10. Click Add Key > Create new key. Select JSON and click Create.
11. Rename the downloaded file to credentials.json and place it in the same folder as your Python script.

