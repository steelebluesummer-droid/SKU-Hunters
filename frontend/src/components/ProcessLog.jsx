import { useEffect, useRef, useState } from 'react';

// 分析过程日志：逐行显现，营造"正在分析"的过程感（数据为冻结 fixture，过程日志即逻辑呈现）
export default function ProcessLog({ lines, speed = 450, onDone }) {
  const [shown, setShown] = useState(0);
  const doneRef = useRef(false);

  useEffect(() => {
    let i = 0;
    const timer = setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= lines.length) {
        clearInterval(timer);
        if (!doneRef.current) { doneRef.current = true; onDone?.(); }
      }
    }, speed);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="process-log">
      {lines.slice(0, shown).map((l, idx) => (
        <div key={idx} className="log-line" style={{ animationDelay: '0s' }}>{l}</div>
      ))}
    </div>
  );
}
