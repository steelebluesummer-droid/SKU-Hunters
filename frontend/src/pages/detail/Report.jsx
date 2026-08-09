import { useEffect, useState } from 'react';
import { Card, Descriptions, Tag, Spin, Alert, Row, Col } from 'antd';
import ReactECharts from 'echarts-for-react';
import { api } from '../../api';

const DIMS = ['趋势热度', '用户需求', 'IP 契合', '竞争格局', '历史类比'];
const DECISION_COLOR = { approve: 'green', hold: 'orange', reject: 'red' };

export default function Report({ sessionId }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let stop = false;
    const tryLoad = async () => {
      while (!stop) {
        try { setReport(await api.getReport(sessionId)); setErr(null); break; }
        catch (e) { if (e?.code === 'REPORT_NOT_READY') { await new Promise(r => setTimeout(r, 1000)); continue; } setErr(e); break; }
      }
      setLoading(false);
    };
    tryLoad();
    return () => { stop = true; };
  }, [sessionId]);

  if (loading) return <Spin />;
  if (err) return <Alert type="warning" message="建议书尚未就绪，等待决策引擎..." />;

  const top = report.proposal;
  const scores = report.opportunity_score;
  const dims = top?.dimension_scores || scores?.dimension_scores || [];
  const radarData = dims.map(d => d.score || 0);

  return (
    <div>
      <Card title={`${top?.name || 'Top1'} ` + (<Tag color={DECISION_COLOR[report.decision]}>{report.decision}</Tag>)} style={{ marginBottom: 16 }}>
        <Descriptions column={2} size="small">
          <Descriptions.Item label="机会值总分">{scores?.total_score?.toFixed(1)} 分</Descriptions.Item>
          <Descriptions.Item label="星级">{'⭐'.repeat(scores?.star_rating || 0)}</Descriptions.Item>
          <Descriptions.Item label="置信度">{report.confidence}</Descriptions.Item>
          <Descriptions.Item label="摘要">{report.summary}</Descriptions.Item>
        </Descriptions>
      </Card>

      {radarData.length > 0 && (
        <Card title="五维雷达图" style={{ marginBottom: 16 }}>
          <ReactECharts option={{
            radar: { indicator: DIMS.map(d => ({ name: d, max: 100 })), center: ['50%', '55%'], radius: '65%' },
            series: [{ type: 'radar', data: [{ value: radarData, name: top?.name || '' }], areaStyle: { opacity: 0.15 } }],
          }} style={{ height: 360 }} />
        </Card>
      )}

      {report.runner_ups?.length > 0 && (
        <Card title="落选方案" size="small" style={{ marginBottom: 16 }}>
          {report.runner_ups.map((r, i) => <Tag key={i}>{r.name}: {r.total_score?.toFixed(1)} 分</Tag>)}
        </Card>
      )}

      {report.conditions?.length > 0 && <Alert type="info" message="前置条件" description={report.conditions.map((c, i) => <div key={i}>• {c}</div>)} style={{ marginBottom: 16 }} />}

      {report.dissent_records?.length > 0 && (
        <Card title="分歧记录" size="small">
          {report.dissent_records.map((d, i) => (
            <Alert key={i} type="warning" message={d.conflict_type} description={d.description} style={{ marginBottom: 8 }} />
          ))}
        </Card>
      )}
    </div>
  );
}
