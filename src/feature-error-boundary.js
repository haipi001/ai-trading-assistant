import React from 'react';

export class FeatureErrorBoundary extends React.Component {
  state = { failed: false, attempt: 0 };
  componentDidMount() { window.dispatchEvent(new window.Event('terminal:feature-mounted')); }
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return React.createElement(React.Fragment, {key: this.state.attempt}, this.props.children);
    return React.createElement('section', {className: 'feature-recovery', role: 'alert'},
      React.createElement('h2', null, '页面暂时无法显示'),
      React.createElement('p', null, '此页面遇到加载或显示问题。其他已打开页面不受影响。'),
      React.createElement('p', null, '重新打开会重置本页临时状态，未保存的修改可能丢失。已保存的设置会保留。'),
      React.createElement('div', {className: 'feature-recovery-actions'},
        React.createElement('button', {type: 'button', onClick: () => this.setState(state => ({failed: false, attempt: state.attempt + 1}))}, '重新打开页面'),
        React.createElement('button', {type: 'button', onClick: () => { if (window.confirm('重新加载本页资源？本页未保存的修改可能丢失。')) window.location.reload(); }}, '重新加载资源')));
  }
}
