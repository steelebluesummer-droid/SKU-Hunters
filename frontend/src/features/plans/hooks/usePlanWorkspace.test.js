/* ============================================================
 * usePlanWorkspace · 洞察生成失败错误保留
 * 失败后保留结构化 error（code/message）；finally 只清 pendingAction，不清 error；
 * 重试成功后 error 清除。
 * ============================================================ */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import usePlanWorkspace from './usePlanWorkspace';

const mockPlans = vi.hoisted(() => ({
  getPlan: vi.fn(),
  generateInsights: vi.fn(),
  generateOpportunities: vi.fn(),
  generatePlanCard: vi.fn(),
  archivePlan: vi.fn(),
  rechooseOpportunity: vi.fn(),
  revisePlan: vi.fn(),
  revisePreview: vi.fn(),
  reviseApply: vi.fn(),
  reviseCancel: vi.fn(),
  reviewPlan: vi.fn(),
}));
vi.mock('../../../api/plans', () => mockPlans);
vi.mock('../../../api/insights', () => ({
  getInsights: vi.fn(),
  getOpportunities: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockPlans.getPlan.mockResolvedValue({
    plan_id: 'p1',
    status: 'brief_locked',
    brief: { category: '小风扇' },
    created_at: '2026-01-01',
  });
});

describe('usePlanWorkspace · 洞察生成失败错误保留', () => {
  it('失败后保留结构化 error（code/message），finally 只清 pendingAction 不清 error', async () => {
    mockPlans.generateInsights.mockRejectedValue({
      status: 503,
      code: 'LLM_UNAVAILABLE',
      message: 'LLM 服务不可用',
      request_id: 'req_abc123',
    });
    const { result } = renderHook(() => usePlanWorkspace('p1'));
    await waitFor(() => expect(result.current.plan).toBeTruthy());

    await act(async () => {
      await expect(result.current.actions.generateInsights()).rejects.toBeTruthy();
    });
    // 保留后端 code/message/request_id（错误编号）
    expect(result.current.error).toEqual(
      expect.objectContaining({
        code: 'LLM_UNAVAILABLE',
        message: 'LLM 服务不可用',
        action: 'insights',
        requestId: 'req_abc123',
      })
    );
    // finally 只清 pendingAction，不清 error
    expect(result.current.pendingAction).toBeNull();
    expect(result.current.error).not.toBeNull();
  });

  it('重试成功后 error 被清除', async () => {
    mockPlans.generateInsights
      .mockRejectedValueOnce({ status: 503, code: 'LLM_UNAVAILABLE', message: 'LLM 服务不可用' })
      .mockResolvedValueOnce({ status: 'insights_ready', insights: {} });
    const { result } = renderHook(() => usePlanWorkspace('p1'));
    await waitFor(() => expect(result.current.plan).toBeTruthy());

    await act(async () => {
      await expect(result.current.actions.generateInsights()).rejects.toBeTruthy();
    });
    expect(result.current.error).not.toBeNull();

    await act(async () => {
      await result.current.actions.generateInsights();
    });
    expect(result.current.error).toBeNull();
    expect(result.current.status).toBe('insights_ready');
  });
});
