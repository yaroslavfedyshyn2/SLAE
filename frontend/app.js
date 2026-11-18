const TOKEN_KEY = "slae_token";

const authView = document.getElementById("auth-view");
const appView = document.getElementById("app-view");
const authForm = document.getElementById("auth-form");
const authError = document.getElementById("auth-error");
const authSubmit = document.getElementById("auth-submit");
const tabLogin = document.getElementById("tab-login");
const tabRegister = document.getElementById("tab-register");

let mode = "login"; // "login" або "register"

// Запит до API. Повертає {status, data}. Кидає Error з текстом, якщо API недоступний.
async function api(path, { method = "GET", body } = {}) {
  const headers = {};
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) headers["Authorization"] = "Bearer " + token;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let resp;
  try {
    resp = await fetch("/api" + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    throw new Error("API недоступний");
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    // порожня або не JSON-відповідь
  }
  return { status: resp.status, data };
}

// Перетворює помилку API на текст. FastAPI: detail це рядок (наші помилки) або список (422).
function errorText(resp) {
  const detail = resp.data && resp.data.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join("; ");
  return "Помилка " + resp.status;
}

function setMode(newMode) {
  if (newMode !== mode) authForm.reset();
  mode = newMode;
  tabLogin.classList.toggle("active", mode === "login");
  tabRegister.classList.toggle("active", mode === "register");
  authSubmit.textContent = mode === "login" ? "Увійти" : "Зареєструватися";
  document.getElementById("password").autocomplete =
    mode === "login" ? "current-password" : "new-password";
  authError.textContent = "";
}

function showAuth() {
  clearTasks();
  appView.hidden = true;
  authView.hidden = false;
}

function showApp(user) {
  authView.hidden = true;
  appView.hidden = false;
  document.getElementById("user-name").textContent = user.username;
  loadTasks().catch((e) => {
    taskError.textContent = e.message;
  });
}

async function login(username, password) {
  const resp = await api("/auth/login", { method: "POST", body: { username, password } });
  if (resp.status !== 200) throw new Error(errorText(resp));
  localStorage.setItem(TOKEN_KEY, resp.data.access_token);
}

async function checkSession() {
  if (!localStorage.getItem(TOKEN_KEY)) {
    showAuth();
    return;
  }
  try {
    const resp = await api("/auth/me");
    if (resp.status === 200) {
      showApp(resp.data);
      return;
    }
    // токен недійсний або прострочений
    localStorage.removeItem(TOKEN_KEY);
  } catch (e) {
    // API недоступний: токен не чіпаємо, показуємо вхід з поясненням
    authError.textContent = e.message;
  }
  showAuth();
}

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";
  authSubmit.disabled = true;

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    if (mode === "register") {
      const resp = await api("/auth/register", { method: "POST", body: { username, password } });
      if (resp.status !== 201) throw new Error(errorText(resp));
    }
    await login(username, password);
    authForm.reset();
    await checkSession();
  } catch (e) {
    authError.textContent = e.message;
  } finally {
    authSubmit.disabled = false;
  }
});

tabLogin.addEventListener("click", () => setMode("login"));
tabRegister.addEventListener("click", () => setMode("register"));

document.getElementById("logout").addEventListener("click", () => {
  localStorage.removeItem(TOKEN_KEY);
  showAuth();
});

const MAX_N = 5000;
const MAX_UPLOAD_BYTES = 300 * 1024 * 1024;

const randomForm = document.getElementById("random-form");
const uploadForm = document.getElementById("upload-form");
const taskError = document.getElementById("task-error");
const taskInfo = document.getElementById("task-info");

// Завантаження файлу: тут не JSON, а multipart, тож api() не підходить.
async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  let resp;
  try {
    resp = await fetch("/api/tasks/upload", {
      method: "POST",
      headers: { Authorization: "Bearer " + localStorage.getItem(TOKEN_KEY) },
      body: form,
    });
  } catch (e) {
    throw new Error("API недоступний");
  }
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {}
  return { status: resp.status, data };
}

function showTaskResult(resp) {
  if (resp.status === 201) {
    taskInfo.textContent = "Задачу створено: №" + resp.data.id + ", n = " + resp.data.n;
    trackTask(resp.data);
  } else {
    taskError.textContent = errorText(resp);
  }
}
function parseN(text) {
  const s = text.trim();
  if (!/^\d+$/.test(s)) return null; 
  const n = Number(s);
  if (n < 1 || n > MAX_N) return null;
  return n;
}
randomForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  taskError.textContent = "";
  taskInfo.textContent = "";

  const n = parseN(document.getElementById("n-input").value);
  if (n === null) {
    taskError.textContent = "n має бути цілим числом від 1 до " + MAX_N;
    return;
  }

  const button = document.getElementById("random-submit");
  button.disabled = true;
  try {
    showTaskResult(await api("/tasks", { method: "POST", body: { n } }));
  } catch (e) {
    taskError.textContent = e.message;
  } finally {
    button.disabled = false;
  }
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  taskError.textContent = "";
  taskInfo.textContent = "";

  const file = document.getElementById("file-input").files[0];
  if (!file) {
    taskError.textContent = "Оберіть файл";
    return;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    taskError.textContent = "Файл завеликий (максимум 300 МБ)";
    return;
  }

  const button = document.getElementById("upload-submit");
  button.disabled = true;
  try {
    showTaskResult(await uploadFile(file));
  } catch (e) {
    taskError.textContent = e.message;
  } finally {
    button.disabled = false;
  }
});
const FINAL_STATUSES = ["DONE", "FAILED", "CANCELLED"];
const STATUS_TEXT = {
  QUEUED: "у черзі",
  RUNNING: "розв'язується",
  DONE: "готово",
  FAILED: "помилка",
  CANCELLED: "скасовано",
};

const taskList = document.getElementById("task-list");
const tasksEmpty = document.getElementById("tasks-empty");

// id задачі -> { id, title, progress, details, error, cancelBtn, socket, finished, timer }
const tasks = new Map();

// Малює стан задачі. Підходить і для відповіді REST, і для події WebSocket (однакові поля).
function updateTask(t, ev) {
  t.title.textContent = "Задача №" + t.id + ": " + (STATUS_TEXT[ev.status] || ev.status);
  t.progress.value = ev.progress;
  t.details.textContent =
    ev.status === "QUEUED"
      ? "Чекає на вільного воркера"
      : "Рядок " + ev.current_row + " з " + ev.n + " (" + ev.progress + "%)";
  t.error.textContent = ev.error || "";
  t.finished = FINAL_STATUSES.includes(ev.status);
  t.cancelBtn.hidden = t.finished;
}

function ensureTask(id, prepend) {
  let t = tasks.get(id);
  if (t) return t;

  const el = document.createElement("li");
  el.className = "task";

  const title = document.createElement("p");
  title.className = "task-title";
  const progress = document.createElement("progress");
  progress.max = 100;
  progress.value = 0;
  const details = document.createElement("p");
  const error = document.createElement("p");
  error.className = "error";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Скасувати";

  el.append(title, progress, details, error, cancelBtn);

  t = { id, title, progress, details, error, cancelBtn, socket: null, finished: false, timer: null };
  cancelBtn.addEventListener("click", () => cancelTask(t));

  if (prepend) taskList.prepend(el);
  else taskList.append(el);
  tasks.set(id, t);
  tasksEmpty.hidden = true;
  return t;
}

function connect(t) {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(proto + "//" + location.host + "/api/ws/tasks/" + t.id);
  t.socket = ws;

  // Токен йде першим повідомленням, а не в URL (так вимагає ws.py)
  ws.onopen = () => ws.send(JSON.stringify({ token: localStorage.getItem(TOKEN_KEY) }));

  ws.onmessage = (msg) => {
    if (t.socket !== ws) return;
    updateTask(t, JSON.parse(msg.data));
  };

  ws.onclose = (e) => {
    if (t.socket !== ws || t.finished) return;
    if (e.code === 4401) {
      localStorage.removeItem(TOKEN_KEY);
      showAuth();
      return;
    }
    if (e.code === 4404) {
      t.error.textContent = "Задачу не знайдено";
      return;
    }
    // Обрив з'єднання: пробуємо знову, сервер пришле знімок стану
    t.timer = setTimeout(() => {
      if (t.socket === ws) connect(t);
    }, 2000);
  };
}

// Закриває всі сокети й очищає список (вихід з акаунта, перезавантаження списку)
function clearTasks() {
  for (const t of tasks.values()) {
    clearTimeout(t.timer);
    const ws = t.socket;
    t.socket = null;
    if (ws) ws.close();
  }
  tasks.clear();
  taskList.replaceChildren();
  tasksEmpty.hidden = false;
}

async function loadTasks() {
  clearTasks();
  const resp = await api("/tasks?limit=50");
  if (resp.status !== 200) {
    taskError.textContent = errorText(resp);
    return;
  }
  for (const task of resp.data) {
    const t = ensureTask(task.id, false);
    updateTask(t, task);
    if (!t.finished) connect(t);
  }
}

function trackTask(task) {
  const t = ensureTask(task.id, true);
  updateTask(t, task);
  if (!t.finished) connect(t);
}

async function cancelTask(t) {
  taskError.textContent = "";
  t.cancelBtn.disabled = true;
  try {
    const resp = await api("/tasks/" + t.id + "/cancel", { method: "POST" });
    // 200: була в черзі, 202: рахується. Новий статус прийде через WebSocket.
    if (resp.status !== 200 && resp.status !== 202) {
      taskError.textContent = errorText(resp);
    }
  } catch (e) {
    taskError.textContent = e.message;
  } finally {
    t.cancelBtn.disabled = false;
  }
}
setMode("login");
checkSession();