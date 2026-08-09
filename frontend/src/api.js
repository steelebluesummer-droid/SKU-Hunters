const BASE = '/api/v1';

async function request(url, opts = {}) {
  const res = await fetch(BASE + url, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw { status: res.status, ...data.detail?.error, ...data };
  return data;
}

export const api = {
  createReview: (brief) => request('/reviews', { method: 'POST', body: { brief } }),
  listReviews: () => request('/reviews'),
  getReview: (id) => request(`/reviews/${id}`),
  getReport: (id) => request(`/reviews/${id}/report`),
  decide: (id, payload) => request(`/reviews/${id}/decision`, { method: 'POST', body: payload }),
  retroChat: (id, question) => request(`/reviews/${id}/retro`, { method: 'POST', body: { question } }),
  weightTemplates: () => request('/weights/templates'),
};
