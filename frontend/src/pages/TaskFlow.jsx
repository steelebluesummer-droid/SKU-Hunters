import { useEffect, useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Steps, Card, Descriptions, Tag, Button, message, Spin, Alert, Empty } from 'antd';
import InsightCockpit from '../components/InsightCockpit';
import OpportunityCards from '../components/OpportunityCards';
import PlanCard from '../components/PlanCard';
import { DEMO_BRIEF } from '../mock/fanData';
import { archivePlan, advancePlan, getPlan, getInsights, getOpportunities } from '../api';

const STEPS = ['企划约束', '洞察驾驶舱', '机会生成', '新品企划卡'];

// 后端 brief 为 snake_case（PlanBrief schema 冻结），前端消费契约统一 camelCase。
const KEY_MAP = {
  price_range: 'priceRange',
  cost_limit: 'costLimit',
  ip_strategy: 'ipStrategy',
  launch_window: 'launchWindow',
};

function normalizeBrief(brief) {
  if (!brief) return null;
  const out = { ...brief };
  for (const [snake, camel] of Object.entries(KEY_MAP)) {
    if (snake in out && !(camel in out)) out[camel] = out[snake];
  }
  // 安全默认值
  out.priceRange = out.priceRange || [39, 99];
  out.costLimit = out.costLimit ?? 25;
  out.ipStrategy = out.ipStrategy || [];
  out.goals = out.goals || [];
  return out;
}

// 任务流程页：约束 → 洞察 → 机会 → 企划卡
// 每个数据块维护独立状态，接口失败不静默回退 mock，而是明确错误 + 重试。
export default function TaskFlow() {
  const nav = useNavigate();
  const { id } = useParams();

  // ── 独立状态块 ─────────────────────────────────────────
  const [plan, setPlan] = useState(null);            // 任务详情（brief / status / plan_card）
  const [insights, setInsights] = useState(null);    // 五看洞察
  const [opportunities, setOpportunities] = useState(null); // 3 张方向卡
  const [oppsLog, setOppsLog] = useState([]);            // 机会生成思考过程
  const [source, setSource] = useState(null);        // 'live' | 'fixture' | 'demo'
  const [planError, setPlanError] = useState(null);
  const [insightsError, setInsightsError] = useState(null);
  const [oppsError, setOppsError] = useState(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [insightsLoading, setInsightsLoading] = useState(false);
  const [oppsLoading, setOppsLoading] = useState(false);

  const [step, setStep] = useState(0);
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [existingCard, setExistingCard] = useState(null);
  const [archiving, setArchiving] = useState(false);

  const isDemo = id === 'demo';
  const brief = plan?.brief ? normalizeBrief(plan.brief) : null;

  // 加载任务详情
  const loadPlan = useCallback(async () => {
    setPlanLoading(true);
    setPlanError(null);
    try {
      const p = await getPlan(id);
      setPlan(p);
      setSource(p?.mode || 'fixture');
      if (p?.selected_opportunity) {
        setSelectedOpp(p.selected_opportunity);
        setStep(3);
        if (p.plan_card) setExistingCard(p.plan_card);
      } else {
        const statusStep = { insights_ready: 1, opportunities_ready: 2 }[p?.status];
        if (statusStep !== undefined) setStep(statusStep);
      }
    } catch (e) {
      setPlanError(e);
      // demo 任务后端离线时，降级到本地演示 brief，但明确标识「演示数据」
      if (isDemo) {
        setPlan({ brief: DEMO_BRIEF, status: 'plan_card_ready', mode: 'fixture' });
        setSource('demo');
      }
    } finally {
      setPlanLoading(false);
    }
  }, [id, isDemo]);

  // 加载洞察
  const loadInsights = useCallback(async () => {
    setInsightsLoading(true);
    setInsightsError(null);
    try {
      const data = await getInsights(id);
      setInsights(data);
    } catch (e) {
      setInsightsError(e);
    } finally {
      setInsightsLoading(false);
    }
  }, [id]);

  // 加载机会卡
  const loadOpportunities = useCallback(async () => {
    setOppsLoading(true);
    setOppsError(null);
    try {
      const data = await getOpportunities(id);
      setOpportunities(data.opportunities || []);
      setOppsLog(data.processLog || []);
    } catch (e) {
      setOppsError(e);
    } finally {
      setOppsLoading(false);
    }
  }, [id]);

  useEffect(() => { loadPlan(); }, [loadPlan]);

  // 进入洞察 / 机会步骤时按需加载对应数据
  const goToStep = useCallback((next) => {
    setStep(next);
    if (next === 1 && !insights) loadInsights();
    if (next === 2 && !opportunities) loadOpportunities();
  }, [insights, opportunities, loadInsights, loadOpportunities]);

  // 显式推进流程状态（GET 只读不推进；推进走 POST advance，见第13点契约）
  const advance = useCallback(async (to) => {
    try {
      await advancePlan(id, to);
      setPlan(p => (p ? { ...p, status: to } : p));
    } catch (e) {
      // 推进失败不阻断数据展示（可能已推进过 / 后端离线），仅提示
      message.warning(`状态推进失败：${e?.message}`);
    }
  }, [id]);

  const archive = async () => {
    setArchiving(true);
    try {
      await archivePlan(id);
      message.success('已归档：企划案进入历史库，可随时复盘追问');
      nav('/');
    } catch (e) {
      message.error(`归档失败：${e.message}`);
    } finally {
      setArchiving(false);
    }
  };

  // 数据来源标识（演示数据必须显式标注）
  const SourceTag = source === 'demo'
    ? <Tag color="orange">演示数据（后端离线）</Tag>
    : (source === 'live' ? <Tag color="green">实时数据</Tag> : <Tag color="blue">冻结 fixture</Tag>);

  if (planLoading) {
    return <div style={{ textAlign: 'center', padding: 80 }}><Spin size="large" /></div>;
  }

  if (planError && !plan) {
    return (
      <Alert
        type="error"
        showIcon
        message="任务加载失败"
        description={planError.message}
        action={<Button size="small" onClick={loadPlan}>重试</Button>}
      />
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>{brief?.theme || '未命名企划'} · {brief?.category || ''}</h2>
        {SourceTag}
      </div>

      <Steps
        current={step}
        onChange={plan?.status === 'archived' ? setStep : goToStep}
        items={STEPS.map(s => ({ title: s }))}
        style={{ marginBottom: 24, maxWidth: 720 }}
      />

      {step === 0 && brief && (
        <Card title="企划约束（由商品经理下达）" style={{ maxWidth: 720 }}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="企划主题">{brief.theme}</Descriptions.Item>
            <Descriptions.Item label="品类">{brief.category}</Descriptions.Item>
            <Descriptions.Item label="目标市场">{brief.market}</Descriptions.Item>
            <Descriptions.Item label="目标人群">{brief.audience}</Descriptions.Item>
            <Descriptions.Item label="价格带">{brief.priceRange[0]}-{brief.priceRange[1]} 元</Descriptions.Item>
            <Descriptions.Item label="成本上限">≤ {brief.costLimit} 元</Descriptions.Item>
            <Descriptions.Item label="IP 策略">{brief.ipStrategy.map(ip => <Tag key={ip} color="red">{ip}</Tag>)}</Descriptions.Item>
            <Descriptions.Item label="上新窗口">{brief.launchWindow || '—'}</Descriptions.Item>
            <Descriptions.Item label="商业目标" span={2}>{brief.goals.map(g => <Tag key={g}>{g}</Tag>)}</Descriptions.Item>
          </Descriptions>
          <Button type="primary" style={{ marginTop: 16 }} onClick={() => { advance('insights_ready'); goToStep(1); }}>确认约束，开始洞察分析</Button>
        </Card>
      )}

      {step === 1 && (
        <div>
          {insightsLoading && <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}
          {insightsError && !insights && (
            <Alert type="error" showIcon message="洞察加载失败" description={insightsError.message}
              action={<Button size="small" onClick={loadInsights}>重试</Button>} />
          )}
          {insights && <InsightCockpit insights={insights} />}
          {!insightsLoading && !insightsError && !insights && (
            <Empty description="暂无洞察数据" />
          )}
          <Button type="primary" style={{ marginTop: 16 }} disabled={!insights} onClick={() => { advance('opportunities_ready'); goToStep(2); }}>
            洞察完成，生成机会方向
          </Button>
        </div>
      )}

      {step === 2 && (
        <div>
          {oppsLoading && <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>}
          {oppsError && !opportunities && (
            <Alert type="error" showIcon message="机会生成失败" description={oppsError.message}
              action={<Button size="small" onClick={loadOpportunities}>重试</Button>} />
          )}
          {opportunities && (
            <OpportunityCards
              opportunities={opportunities}
              selected={selectedOpp}
              onSelect={plan?.status === 'archived' ? () => {} : setSelectedOpp}
              processLog={oppsLog}
            />
          )}
          {!oppsLoading && !oppsError && !opportunities && (
            <Empty description="暂无机会方向" />
          )}
          <Button type="primary" style={{ marginTop: 16 }} disabled={!selectedOpp} onClick={() => setStep(3)}>
            进入企划生成（概念设计 + 商品策略）
          </Button>
        </div>
      )}

      {step === 3 && (
        <div>
          <PlanCard opportunity={opportunities?.find(o => o.id === selectedOpp)} existingCard={existingCard} planId={id} brief={brief || DEMO_BRIEF} />
          <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
            {plan?.status === 'archived' ? (
              <>
                <Tag>已归档 · 复盘追问可用右下角改稿沟通</Tag>
                <Button onClick={() => nav('/')}>返回任务中心</Button>
              </>
            ) : (
              <>
                <Button onClick={() => setStep(2)}>返回换方向</Button>
                <Button type="primary" loading={archiving} onClick={archive}>归档企划案</Button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
