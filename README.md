# Expense backend

The backend reads `../Expensesanlayser/.env` using an absolute path. Keep:

```dotenv
MONGODB_URI=your-connection-string
DATABASE_NAME=expense_analyser
EXPENSES_COLLECTION=expenses
```

Do not prefix MongoDB settings with `EXPO_PUBLIC_`; the mobile app only calls the Python API.

From this backend folder, in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

In another terminal:

```powershell
cd D:\APPs\IOS\Expensesanlayser
npx expo start --clear
```

In Expo Go, the app discovers the development computer from Expo and calls port 8001. Keep the computer and phone on the same network and allow that port through the firewall. For an Expo tunnel or a different backend host, add `EXPO_PUBLIC_API_URL=http://YOUR_COMPUTER_LAN_IP:8001` to the same `.env`, then fully reload Expo. Production builds require an explicit HTTPS API URL.

`GET /health` checks that the server started. `POST /expenses` validates and saves an expense. The date is a local calendar date (`YYYY-MM-DD`); amount is stored as MongoDB Decimal128. Item name and category are required; amount must be positive with at most two decimal places and twelve total digits.

The form clears only after a successful save. If a request times out, inspect MongoDB before retrying because a write may already have completed.

This API is intended for local development. Add authentication before exposing it publicly.

## Hosting configuration

Deploy only `IOS/ExpensesanlayserBackend`. Set these secrets in the host's environment settings; the local frontend `.env` is not included in deployment:

- `MONGODB_URI`: your MongoDB connection string
- `DATABASE_NAME`: your database name
- `EXPENSES_COLLECTION`: your expenses collection
- `CORS_ORIGINS`: comma-separated frontend origins if serving the app on the web

Build command: `pip install -r requirements.txt`

Start command: `python start.py`

Health check path: `/health`

The start script binds to `0.0.0.0` and uses the host's `PORT` (8001 locally). A Dockerfile is also included; use this backend folder as its build context. It copies only the API source and never includes `.env`.

Allow the deployed service's outbound addresses in MongoDB Atlas Network Access. Once the service is live, set `EXPO_PUBLIC_API_URL` in `Expensesanlayser/.env` to its HTTPS URL and fully reload Expo Go.

## Render

Create a Python Web Service connected to your Git repository. Use:

| Setting | Value |
| --- | --- |
| Language | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `python start.py` |
| Health check path | `/health` |

Root Directory must point to this backend folder **relative to the Git repository root**: `IOS/ExpensesanlayserBackend` if the repository contains the whole `APPs` workspace, `ExpensesanlayserBackend` if it contains `IOS`, or leave it empty for a backend-only repository.

Add the three MongoDB environment variables above through Render's Environment settings. Never upload the local `.env`. Native mobile requests do not require a CORS origin; for a web frontend, set `CORS_ORIGINS` to its exact HTTPS origin.

Once deployed, open `https://YOUR-SERVICE.onrender.com/health` and confirm `{"status":"ok"}`. Then update the frontend `EXPO_PUBLIC_API_URL` to `https://YOUR-SERVICE.onrender.com` and fully reload the app. Keep MongoDB settings private and unchanged.

Render setup reference: https://render.com/docs/deploy-fastapi

## Expense List

`GET /expenses?year=2026&month=11&limit=50&offset=0` returns `items`, `has_more`, `total_amount`, `total_count`, and `available_years`. Each item contains `id`, `item_name`, `date`, `category`, and `amount` (a decimal string). Results sort by date descending, then creation time and ID descending. `limit` accepts 1–100; `offset` must be nonnegative. A month requires a year. Omitting both returns all dates for compatibility.

The total and count cover every matching expense, independent of the page size. Amounts are summed as decimals in MongoDB. Available years come from all saved expense dates. The screen starts with the current local year/month, updates automatically on selection, and displays a horizontally scrollable table on narrow screens. An empty month has total `0.00`.

Test locally first: run the backend with `--reload`, point `EXPO_PUBLIC_API_URL` at the computer's LAN address on port 8001, and reload Expo Go. The screen reloads when opened and supports refresh and loading additional pages. Once local testing is complete, deploy the backend before the frontend. Keep Render's `CORS_ORIGINS` updated for the frontend deployment URL.

### Column filters

Each table header opens a searchable list of values for that column. Select multiple values and press Apply; columns combine with AND, while values within one column combine with OR. No selection leaves the column unrestricted. Active buttons are highlighted. Filters reset when the year or month changes.

The API accepts `filters` as a URL-encoded JSON object with optional `item_name`, `date`, `category`, `comments`, and `amount` arrays. Dates use `YYYY-MM-DD`; amounts use decimal strings. For example: `{"item_name":["Lunch","Dinner"],"category":["Food"]}`. The response includes `filter_options` covering all records in the selected period, independently of pagination and active column filters. Totals and counts reflect the combined filters across all pages. Blank comments also match older records without a comments field.
