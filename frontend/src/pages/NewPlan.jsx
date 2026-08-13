import { useNavigate } from 'react-router-dom';
import { Form, Select, Input, InputNumber, Button, Card, Checkbox, message } from 'antd';
import { DEMO_BRIEF } from '../mock/fanData';
import { createPlan } from '../api';

// 企划启动：约束输入（对应名创"年度品类规划 → 企划案"的约束下达）
export default function NewPlan() {
  const nav = useNavigate();

  const onFinish = async (values) => {
    // 接后端：按表单创建真实任务（品类决定洞察数据源，见 get_insights）
    const brief = {
      theme: values.theme,
      category: values.category,
      market: values.market || DEMO_BRIEF.market,
      audience: values.audience || '',
      price_range: [values.priceMin ?? DEMO_BRIEF.priceRange[0], values.priceMax ?? DEMO_BRIEF.priceRange[1]],
      cost_limit: values.costLimit ?? DEMO_BRIEF.costLimit,
      ip_strategy: values.ipStrategy || [],
      launch_window: values.launchWindow || '',
      goals: values.goals || [],
    };
    message.loading({ content: '正在创建企划…', key: 'create' });
    const res = await createPlan(brief);
    if (res && res.plan_id) {
      message.success({ content: '企划已创建，进入洞察', key: 'create' });
      nav(`/tasks/${res.plan_id}`);
    } else {
      message.error({ content: '创建失败：后端可能不在线', key: 'create' });
    }
  };

  return (
    <Card title="新建新品企划" style={{ maxWidth: 640 }}
      extra={<span style={{ color: '#999', fontSize: 12 }}>约束由商品经理下达，AI 在约束内做有依据的创意</span>}>
      <Form layout="vertical" onFinish={onFinish}
        initialValues={{
          theme: DEMO_BRIEF.theme,
          category: DEMO_BRIEF.category,
          market: DEMO_BRIEF.market,
          audience: DEMO_BRIEF.audience,
          priceMin: DEMO_BRIEF.priceRange[0],
          priceMax: DEMO_BRIEF.priceRange[1],
          costLimit: DEMO_BRIEF.costLimit,
          ipStrategy: DEMO_BRIEF.ipStrategy,
          launchWindow: DEMO_BRIEF.launchWindow,
          goals: DEMO_BRIEF.goals,
        }}>
        <Form.Item label="企划主题" name="theme" rules={[{ required: true, message: '必填' }]}>
          <Input placeholder="如 2027夏季户外生活系列" />
        </Form.Item>
        <Form.Item label="品类" name="category" rules={[{ required: true, message: '必填' }]}>
          <Select options={['小风扇', '保温杯', '香薰', '桌面摆件', '雨伞', '冰袖'].map(c => ({ value: c, label: c }))} />
        </Form.Item>
        <Form.Item label="目标市场" name="market">
          <Select options={['中国大陆', '东南亚', '日本', '欧美'].map(m => ({ value: m, label: m }))} />
        </Form.Item>
        <Form.Item label="目标人群" name="audience">
          <Input placeholder="如 18-30岁年轻女性" />
        </Form.Item>
        <div style={{ display: 'flex', gap: 16 }}>
          <Form.Item label="价格带下限（元）" name="priceMin" style={{ flex: 1 }}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="价格带上限（元）" name="priceMax" style={{ flex: 1 }}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="成本上限（元）" name="costLimit" style={{ flex: 1 }}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
        </div>
        <Form.Item label="IP 策略" name="ipStrategy">
          <Checkbox.Group options={['三丽鸥', '迪士尼', 'Chiikawa', '线条小狗', '不带 IP']} />
        </Form.Item>
        <Form.Item label="上新窗口" name="launchWindow">
          <Input placeholder="如 2027年5月（夏季前）" />
        </Form.Item>
        <Form.Item label="商业目标" name="goals">
          <Checkbox.Group options={['夏季销售提升', '打造IP爆款', '拓展新人群', '提升连带率']} />
        </Form.Item>
        <Button type="primary" htmlType="submit" block>创建企划，进入洞察</Button>
      </Form>
    </Card>
  );
}
