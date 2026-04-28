IBM Cloud deployment steps

1. Install IBM Cloud CLI and Cloud Foundry plugin.
2. Login: ibmcloud login -a cloud.ibm.com -r au-syd
3. Target a resource group if needed: ibmcloud target -g Default
4. Install CF plugin if needed: ibmcloud cf install
5. From this folder run: ibmcloud cf push
6. Open the route shown after deployment.

Notes:
- This app uses SQLite. On Cloud Foundry, SQLite storage is ephemeral and may reset after restage or redeploy.
- Do not upload your local env/ or node_modules/ folders.
- If you want IBM App ID login, set environment variables in the app after deployment instead of shipping .env.
