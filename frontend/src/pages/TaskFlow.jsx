import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Steps, Card, Descriptions, Tag, Button, message } from 'antd';
import InsightCockpit from '../components/InsightCockpit';
import OpportunityCards from '../components/OpportunityCards';
import PlanCard from '../components/PlanCard';
import { DEMO_BRIEF } from '../mock/fanData';
import { archivePlan, getPlan } from '../api';

const STEPS = ['企划约束', '洞察驾驶舱', '机会生成', '新品企划卡'];

// 任务流程页：约束 → 洞察 → 机会 → 企划卡（mock 阶段全部读取 fixture）
export default function TaskFlow() {
  const [step, setStep] = useState(0);
  const [selectedOpp, setSelectedOpp] = useState(null);
  const [planStatus, setPlanStatus] = useState(null);
  const [existingCard, setExistingCard] = useState(null);  // 已有企划卡（归档后回看）
  const [archiving, setArchiving] = useState(false);
  const nav = useNavigate();
  const { id } = useParams();  // URL 中的任务 id（/tasks/:id），不再是固定 demo

  // 进入任务时从后端恢复进度：已选过方向（含已归档）→ 直接落到新品企划卡
  useEffect(() => {
    getPlan(id).then(plan => {
      if (!plan) return;
      setPlanStatus(plan.status);
      if (plan.selected_opportunity) {
        setSelectedOpp(plan.selected_opportunity);
        setStep(3);
        // 如果后端已有企划卡数据，直接复用，不再调 generatePlanCard
        if (plan.plan_card) {
          setExistingCard(plan.plan_card);
        }
      } else {
        // 未选方向：按后端状态恢复到对应步骤（如 Aily 发起的任务已跑完洞察+机会 → 落到机会生成）
        const statusStep = { insights_ready: 1, opportunities_ready: 2 }[plan.status];
        if (statusStep !== undefined) setStep(statusStep);
      }
    });
  }, []);

  const archive = async () => {
    setArchiving(true);
    const status = await archivePlan(id);
    setArchiving(false);
    if (status === 'archived') {
      message.success('已归档：企划案进入历史库，可随时复盘追问');
    } else {
      message.warning('后端不在线，归档状态未保存（本次仅页面跳转）');
    }
    nav('/');
  };

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>{DEMO_BRIEF.theme} · {DEMO_BRIEF.category}</h2>
      </div>
      <Steps
        current={step}
        // 已归档任务：默认落在企划卡，但 1/2/3 步可点击回看
        onChange={planStatus === 'archived' ? setStep : undefined}
        items={STEPS.map(s => ({ title: s }))}
        style={{ marginBottom: 24, maxWidth: 720 }}
      />

      {step === 0 && (
        <Card title="企划约束（由商品经理下达）" style={{ maxWidth: 720 }}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="企划主题">{DEMO_BRIEF.theme}</Descriptions.Item>
            <Descriptions.Item label="品类">{DEMO_BRIEF.category}</Descriptions.Item>
            <Descriptions.Item label="目标市场">{DEMO_BRIEF.market}</Descriptions.Item>
            <Descriptions.Item label="目标人群">{DEMO_BRIEF.audience}</Descriptions.Item>
            <Descriptions.Item label="价格带">{DEMO_BRIEF.priceRange[0]}-{DEMO_BRIEF.priceRange[1]} 元</Descriptions.Item>
            <Descriptions.Item label="成本上限">≤ {DEMO_BRIEF.costLimit} 元</Descriptions.Item>
            <Descriptions.Item label="IP 策略">{DEMO_BRIEF.ipStrategy.map(i => <Tag key={i} color="red">{i}</Tag>)}</Descriptions.Item>
            <Descriptions.Item label="上新窗口">{DEMO_BRIEF.launchWindow}</Descriptions.Item>
            <Descriptions.Item label="商业目标" span={2}>{DEMO_BRIEF.goals.map(g => <Tag key={g}>{g}</Tag>)}</Descriptions.Item>
          </Descriptions>
          <Button type="primary" style={{ marginTop: 16 }} onClick={() => setStep(1)}>确认约束，开始洞察分析</Button>
        </Card>
      )}

      {step === 1 && (
        <div>
          <InsightCockpit />
          <Button type="primary" style={{ marginTop: 16 }} onClick={() => setStep(2)}>洞察完成，生成机会方向</Button>
        </div>
      )}

      {step === 2 && (
        <div>
          <OpportunityCards selected={selectedOpp} onSelect={planStatus === 'archived' ? () => {} : setSelectedOpp} />
          <Button type="primary" style={{ marginTop: 16 }} disabled={!selectedOpp} onClick={() => setStep(3)}>
            进入企划生成（概念设计 + 商品策略）
          </Button>
        </div>
      )}

      {step === 3 && (
        <div>
          <PlanCard opportunityId={selectedOpp} existingCard={existingCard} planId={id} />
          <div style={{ marginTop: 16, display: 'flex', gap: 8, alignItems: 'center' }}>
            {planStatus === 'archived' ? (
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
