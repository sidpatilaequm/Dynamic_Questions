const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

/** Thrown for any non-2xx reply. `fieldErrors` is keyed by question id. */
export class ApiError extends Error {
  constructor(message, { status, fieldErrors } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.fieldErrors = fieldErrors ?? null;
  }
}

async function request(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('The server is not responding. Check that the API is running.');
  }

  if (res.status === 204) return null;

  let payload = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }

  if (res.ok) return payload;

  const detail = payload?.detail;

  // Submission failures arrive as { message, errors: { questionId: text } }
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && detail.errors) {
    throw new ApiError(detail.message ?? 'Some answers still need attention.', {
      status: res.status,
      fieldErrors: detail.errors,
    });
  }

  // Pydantic validation errors arrive as a list
  if (Array.isArray(detail)) {
    const first = detail[0];
    throw new ApiError(first?.msg ?? `Request failed (${res.status})`, { status: res.status });
  }

  throw new ApiError(
    typeof detail === 'string' ? detail : `Request failed (${res.status})`,
    { status: res.status },
  );
}

export const api = {
  listProcesses: () => request('/processes'),
  createProcess: (body) => request('/processes', { method: 'POST', body }),
  getProcess: (id) => request(`/processes/${id}`),
  updateProcess: (id, body) => request(`/processes/${id}`, { method: 'PUT', body }),
  deleteProcess: (id) => request(`/processes/${id}`, { method: 'DELETE' }),
  duplicateProcess: (id) => request(`/processes/${id}/duplicate`, { method: 'POST' }),
  activateProcess: (id, key) =>
    request(`/processes/${id}/activate?key=${encodeURIComponent(key)}`, { method: 'PATCH' }),

  createSection: (processId, body) =>
    request(`/processes/${processId}/sections`, { method: 'POST', body }),
  updateSection: (id, body) => request(`/sections/${id}`, { method: 'PUT', body }),
  deleteSection: (id) => request(`/sections/${id}`, { method: 'DELETE' }),
  reorderSections: (processId, sectionIds) =>
    request(`/processes/${processId}/sections/order`, {
      method: 'PUT',
      body: { section_ids: sectionIds },
    }),

  createQuestion: (sectionId, body) =>
    request(`/sections/${sectionId}/questions`, { method: 'POST', body }),
  updateQuestion: (id, body) => request(`/questions/${id}`, { method: 'PUT', body }),
  deleteQuestion: (id) => request(`/questions/${id}`, { method: 'DELETE' }),
  reorderQuestions: (sectionId, questionIds) =>
    request(`/sections/${sectionId}/questions/order`, {
      method: 'PUT',
      body: { question_ids: questionIds },
    }),

  submitResponse: (processId, body) =>
    request(`/processes/${processId}/responses`, { method: 'POST', body }),
  listResponses: (processId) => request(`/processes/${processId}/responses`),
  deleteResponse: (id) => request(`/responses/${id}`, { method: 'DELETE' }),
};

export const QUESTION_TYPES = [
  {
    value: 'short_text',
    name: 'Short answer',
    hint: 'A single line of free text.',
    tag: 'TEXT',
  },
  {
    value: 'single_choice',
    name: 'Single choice',
    hint: 'Options, one of which can be picked.',
    tag: 'ONE',
  },
  {
    value: 'multi_choice',
    name: 'Multiple choice',
    hint: 'Options, any number of which can be picked.',
    tag: 'MANY',
  },
];

export const typeInfo = (value) =>
  QUESTION_TYPES.find((t) => t.value === value) ?? QUESTION_TYPES[0];
