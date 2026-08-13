/* ============================================================
 * SKU Hunters · PageHeader（页面头部）
 * 标题 + 可选副标题 + 右侧操作区（主 CTA）。
 * 窄屏（375）下操作区自动换行，避免挤压标题。
 * ============================================================ */

export default function PageHeader({ title, subtitle, extra }) {
  return (
    <div
      style={{
        marginBottom: 20,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        gap: 16,
        flexWrap: 'wrap',
      }}
    >
      <div style={{ minWidth: 0 }}>
        <h2 style={{ margin: 0, wordBreak: 'break-word' }}>{title}</h2>
        {subtitle ? (
          <p style={{ margin: '4px 0 0', color: '#666', fontSize: 13 }}>{subtitle}</p>
        ) : null}
      </div>
      {extra ? <div style={{ flexShrink: 0 }}>{extra}</div> : null}
    </div>
  );
}
