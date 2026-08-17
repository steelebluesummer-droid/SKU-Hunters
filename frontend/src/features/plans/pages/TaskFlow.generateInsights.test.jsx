/* ============================================================
 * TaskFlow · 洞察生成失败可见性（失败不跳步 / 错误卡片 / 重试 / 成功才进入下一步）
 * ============================================================ */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import TaskFlow from './TaskFlow';

// ── mock 懒加载的真实组件（echarts 等重依赖不在 jsdom 加载）────
vi.mock('../../insights/InsightCockpit', () => ({
  default: () => <div data-testid="mock-cockpit">MockInsightCockpit</div>,
}));
vi.mock('../../insights/InsightGeneratingSteps', () => ({
  default: () => <div>生成中…</div>,
}));

// ── mock API 模块 ────────────────────────────────────────
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

const brief = {
  theme: '2027夏季户外系列',
  category: '小风扇',
  market: '国内市场',
  audience: '年轻消费者',
  price_range: [39, 99],
  cost_limit: 25,
  ip_strategy: [],
  launch_window: '2027Q2',
  goals: ['提升销量'],
};

function planObj(status = 'brief_locked') {
  return {
    plan_id: 'p1',
    status,
    brief,
    mode: 'fixture',
    created_at: '2026-01-01',
  };
}

function renderFlow() {
  return render(
    <MemoryRouter initialEntries={['/plans/p1']}>
      <Routes>
        <Route path="/plans/:id" element={<TaskFlow />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPlans.getPlan.mockResolvedValue(planObj('brief_locked'));
});

describe('TaskFlow · 洞察生成失败可见性', () => {
  it('接口成功且返回 status=insights_ready 才进入下一步（洞察驾驶舱）', async () => {
    mockPlans.generateInsights.mockResolvedValue({ status: 'insights_ready', insights: {} });
    renderFlow();
    fireEvent.click(await screen.findByText('确认约束，开始洞察分析'));
    await waitFor(() => {
      expect(mockPlans.generateInsights).toHaveBeenCalledTimes(1);
    });
    // 进入第 1 步：显示「生成机会方向」按钮
    expect(await screen.findByText('洞察完成，生成机会方向')).toBeInTheDocument();
    // 第 0 步按钮消失
    expect(screen.queryByText('确认约束，开始洞察分析')).not.toBeInTheDocument();
  });

  it('接口成功但 status 非 insights_ready 时不跳步', async () => {
    mockPlans.generateInsights.mockResolvedValue({ status: 'brief_locked', insights: {} });
    renderFlow();
    fireEvent.click(await screen.findByText('确认约束，开始洞察分析'));
    await waitFor(() => {
      expect(mockPlans.generateInsights).toHaveBeenCalledTimes(1);
    });
    // 仍留在第 0 步
    expect(screen.getByText('确认约束，开始洞察分析')).toBeInTheDocument();
    expect(screen.queryByText('洞察完成，生成机会方向')).not.toBeInTheDocument();
  });

  it('失败不跳步，并展示 code + message 错误卡片', async () => {
    mockPlans.generateInsights.mockRejectedValue({
      status: 503,
      code: 'LLM_UNAVAILABLE',
      message: 'LLM 服务不可用',
    });
    renderFlow();
    fireEvent.click(await screen.findByText('确认约束，开始洞察分析'));
    await waitFor(() => {
      expect(mockPlans.generateInsights).toHaveBeenCalledTimes(1);
    });
    // 错误卡片：code + message
    expect(await screen.findByText('洞察生成失败（LLM_UNAVAILABLE）')).toBeInTheDocument();
    expect(screen.getByText('LLM 服务不可用')).toBeInTheDocument();
    // 仍停留在第 0 步，未进入第 1 步
    expect(screen.getByText('确认约束，开始洞察分析')).toBeInTheDocument();
    expect(screen.queryByText('洞察完成，生成机会方向')).not.toBeInTheDocument();
  });

  it('点击重试按钮可重新发起生成，成功后进入下一步', async () => {
    mockPlans.generateInsights
      .mockRejectedValueOnce({ status: 503, code: 'LLM_UNAVAILABLE', message: 'LLM 服务不可用' })
      .mockResolvedValueOnce({ status: 'insights_ready', insights: {} });
    renderFlow();
    fireEvent.click(await screen.findByText('确认约束，开始洞察分析'));
    await screen.findByText('洞察生成失败（LLM_UNAVAILABLE）');
    // 点重试 → 重新发起
    fireEvent.click(screen.getByTestId('insight-retry'));
    await waitFor(() => {
      expect(mockPlans.generateInsights).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('洞察完成，生成机会方向')).toBeInTheDocument();
    // 错误卡片已清除
    expect(screen.queryByText('洞察生成失败（LLM_UNAVAILABLE）')).not.toBeInTheDocument();
  });
});
