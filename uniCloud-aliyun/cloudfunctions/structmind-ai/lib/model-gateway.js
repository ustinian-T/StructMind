'use strict';

const { aiError } = require('./provider-catalog');

function joinURL(base, suffix) {
  return `${String(base).replace(/\/+$/, '')}/${String(suffix).replace(/^\/+/, '')}`;
}

function authHeaders(credential) {
  const headers = { 'Content-Type': 'application/json' };
  if (credential.protocol === 'anthropic') headers['anthropic-version'] = '2023-06-01';
  if (credential.auth_style === 'x-api-key') headers['x-api-key'] = credential.api_key;
  else headers.Authorization = `Bearer ${credential.api_key}`;
  return headers;
}

function normalizedMessages(messages) {
  return (Array.isArray(messages) ? messages : [])
    .filter(item => item && ['system', 'user', 'assistant'].includes(item.role))
    .map(item => ({ role: item.role, content: String(item.content || '') }));
}

function anthropicRequest(credential, options) {
  const allMessages = normalizedMessages(options.messages);
  const system = allMessages.filter(item => item.role === 'system').map(item => item.content).join('\n\n');
  const messages = allMessages.filter(item => item.role !== 'system');
  const data = {
    model: credential.model_id,
    messages,
    max_tokens: Math.max(1, Math.min(Number(options.maxTokens || 1200), 8192)),
    temperature: Number.isFinite(options.temperature) ? options.temperature : 0.2,
    stream: false,
  };
  if (system) data.system = system;
  if (Array.isArray(options.tools) && options.tools.length) {
    data.tools = options.tools.map(tool => ({
      name: tool.function?.name || tool.name,
      description: tool.function?.description || tool.description || '',
      input_schema: tool.function?.parameters || tool.input_schema || { type: 'object', properties: {} },
    }));
  }
  return { url: joinURL(credential.base_url, 'v1/messages'), data };
}

function openAIRequest(credential, options) {
  const data = {
    model: credential.model_id,
    messages: normalizedMessages(options.messages),
    max_tokens: Math.max(1, Math.min(Number(options.maxTokens || 1200), 8192)),
    temperature: Number.isFinite(options.temperature) ? options.temperature : 0.2,
    stream: false,
  };
  if (Array.isArray(options.tools) && options.tools.length) {
    data.tools = options.tools;
    data.tool_choice = 'auto';
  }
  return { url: joinURL(credential.base_url, 'chat/completions'), data };
}

function parseData(value) {
  if (Buffer.isBuffer(value)) value = value.toString('utf8');
  if (typeof value === 'string') {
    try { return JSON.parse(value); }
    catch (_error) { return {}; }
  }
  return value && typeof value === 'object' ? value : {};
}

function normalizeUpstreamError(status, error) {
  if (status === 401 || status === 403) return aiError('AI_CREDENTIAL_INVALID', 'API Key 无效或没有该模型权限。');
  if (status === 429) return aiError('AI_QUOTA_EXCEEDED', '模型额度不足或请求过于频繁，请稍后重试。');
  const message = String(error?.message || error || '').toLowerCase();
  if (message.includes('timeout') || message.includes('timed out')) {
    return aiError('AI_PROVIDER_TIMEOUT', '模型响应超时，请稍后重试。');
  }
  return aiError('AI_PROVIDER_UNAVAILABLE', '模型服务暂时不可用，请稍后重试。');
}

function parseAnthropic(data, credential) {
  const blocks = Array.isArray(data.content) ? data.content : [];
  const content = blocks.filter(block => block?.type === 'text' && typeof block.text === 'string')
    .map(block => block.text).join('');
  const toolCalls = blocks.filter(block => block?.type === 'tool_use').map(block => ({
    id: block.id || '', name: block.name || '', arguments: block.input || {},
  }));
  if (!content && !toolCalls.length) throw normalizeUpstreamError(502);
  return {
    content, tool_calls: toolCalls,
    usage: {
      input_tokens: Number(data.usage?.input_tokens || 0),
      output_tokens: Number(data.usage?.output_tokens || 0),
    },
    finish_reason: data.stop_reason || 'stop',
    provider_id: credential.provider_id, model_id: credential.model_id,
  };
}

function parseOpenAI(data, credential) {
  const choice = data.choices?.[0];
  if (!choice) throw normalizeUpstreamError(502);
  const message = choice.message || {};
  const toolCalls = (message.tool_calls || []).map(call => ({
    id: call.id || '', name: call.function?.name || '',
    arguments: (() => {
      try { return JSON.parse(call.function?.arguments || '{}'); }
      catch (_error) { return {}; }
    })(),
  }));
  return {
    content: typeof message.content === 'string' ? message.content : '',
    tool_calls: toolCalls,
    usage: {
      input_tokens: Number(data.usage?.prompt_tokens || 0),
      output_tokens: Number(data.usage?.completion_tokens || 0),
    },
    finish_reason: choice.finish_reason || 'stop',
    provider_id: credential.provider_id, model_id: credential.model_id,
  };
}

async function callModel({
  httpclient, credential, messages = [], tools = null,
  temperature = 0.2, maxTokens = 1200,
}) {
  const request = credential.protocol === 'anthropic'
    ? anthropicRequest(credential, { messages, tools, temperature, maxTokens })
    : openAIRequest(credential, { messages, tools, temperature, maxTokens });
  let response;
  try {
    response = await httpclient.request(request.url, {
      method: 'POST', headers: authHeaders(credential), data: request.data,
      dataType: 'json', timeout: Math.min(Number(credential.timeout_ms || 120000), 120000),
    });
  } catch (error) {
    throw normalizeUpstreamError(0, error);
  }
  const status = Number(response.status || response.statusCode || 0);
  const data = parseData(response.data);
  if (status < 200 || status >= 300) throw normalizeUpstreamError(status);
  return credential.protocol === 'anthropic'
    ? parseAnthropic(data, credential)
    : parseOpenAI(data, credential);
}

module.exports = { callModel, normalizeUpstreamError };
