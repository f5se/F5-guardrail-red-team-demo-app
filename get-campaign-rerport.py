from calypsoai import CalypsoAI

# Define the URL and token for CalypsoAI
CALYPSOAI_URL = "https://www.us1.calypsoai.app"
CALYPSOAI_TOKEN = "MDE5OWRjZTYtN2Y1Zi03MDRiLWExMjMtZWNkODMwZjg0MjYz/HIw7Hp5VToME5BdArWPqforqjXIHdMz2Ml60BpGefLxg4TeAIFCHNnzbBAJW3ncGU8GjDp5gKVt3bj5oH2iUg"

# Initialize the CalypsoAI client
cai = CalypsoAI(url=CALYPSOAI_URL, token=CALYPSOAI_TOKEN)

# Get the list of campaign runs
runs = cai.client.campaignRuns.get()

# Get a report
cai.campaigns.getReport(campaignRun='0199697b-fe67-709f-9088-af7b3702fe1a', output='./')