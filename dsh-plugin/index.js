/**
 * dsh-vocab-app 宿主半（Node ESM / cordis 插件入口）。
 *
 * 只注册两个 exact Fetch 路由（精确路径 + buffered 请求体）：
 *   GET  /api/vocab-app/state
 *   POST /api/vocab-app/action
 *
 * 生命周期分两层，任何一步失败或卸载都必须释放记录锁：
 *  1) 独立 effect 只负责 engine.close()（引擎在 ready() 里同步取进程锁，
 *     所以注册路由失败时也必须能关闭它）；
 *  2) 路由 effect 在 try/catch 中注册：部分注册失败时先注销已注册路由、
 *     再 engine.close()、再抛出；卸载 cleanup 用 try/finally 保证即使某个
 *     disposer 抛错也一定执行 engine.close()。
 *  3) 连 ctx.effect 自身注册失败也兜底：外层 catch 仍注销已成功路由并关闭 engine。
 *
 * 不 import 任何 @deepseek-ai/* 包；宿主能力全部来自 ctx 服务。
 */
import { Engine } from './lib/host/engine.js';
import { createHandlers, STATE_PATH, ACTION_PATH } from './lib/host/http.js';
import { normalizeNamespace } from './lib/host/store.js';

export const name = 'vocab-app';
export const inject = ['connection'];

function logIfAvailable(ctx, level, message) {
  try {
    const logger = ctx && ctx.logger;
    if (logger && typeof logger[level] === 'function') logger[level](message);
  } catch {
    /* 日志通道不可用时不阻断插件 */
  }
}

function closeEngineQuietly(engine) {
  try {
    engine.close();
  } catch {
    /* close 幂等且不应阻断卸载 */
  }
}

/** 只记一条首次警告，避免卸载路径刷屏。 */
function warningSink(ctx) {
  const seen = new Set();
  return (message) => {
    if (seen.has(message)) return;
    seen.add(message);
    logIfAvailable(ctx, 'warn', message);
  };
}

/**
 * @param {object} ctx cordis 宿主上下文（需提供 connection.fetch.register 与 effect）
 * @param {{dataNamespace?:string, dataDir?:string, homeDir?:string}} [config]
 */
export function apply(ctx, config = {}) {
  const connection = ctx && ctx.connection;
  if (!connection || !connection.fetch || typeof connection.fetch.register !== 'function') {
    throw new Error('dsh-vocab-app 需要 ctx.connection.fetch 服务；当前宿主未启用 connection。');
  }
  // 命名空间在插件加载阶段校验：不合法立即失败，避免运行期悄悄写到别的文件。
  const dataNamespace = normalizeNamespace(config && config.dataNamespace);
  const engine = new Engine({
    config: {
      dataNamespace,
      dataDir: config && config.dataDir,
      homeDir: config && config.homeDir,
    },
  });
  const warn = warningSink(ctx);
  // engine.ready() 会同步取进程锁、再异步加载数据；从这里开始任何失败路径
  // 都必须保证 engine.close()，否则卸载/注册失败会泄漏锁。
  const ready = engine.ready();
  // 启动失败的细节在请求时以 503 暴露；这里只记录一次，不让 unhandled rejection
  // 冒泡。插件在加载过程中被卸载属于正常路径（engine.close 已释放记录锁），不记错误。
  ready.catch((error) => {
    if (engine.closed || (error && error.code === 'conflict')) return;
    logIfAvailable(
      ctx,
      'error',
      `dsh-vocab-app 记录加载失败：${error && error.message ? error.message : error}`,
    );
  });
  const handlers = createHandlers({ engine });

  // 独立生命周期 effect：与路由注册解耦。注册路由抛错时 cordis 若销毁本插件
  // fiber，这一层 cleanup 也会关闭 engine；路由 effect 的 catch 里还会先关一次。
  // ctx.effect 自身抛错时也必须关掉已取到的锁。
  try {
    ctx.effect(() => () => closeEngineQuietly(engine), 'dsh-vocab-app: engine lifecycle');
  } catch (error) {
    closeEngineQuietly(engine);
    throw error;
  }

  // 已注册路由的 disposer 由 apply 闭包持有：无论 factory、个别 register、还是
  // ctx.effect 自身失败，都能在同一个幂等函数里先注销路由、再关闭 engine。
  const disposers = [];
  let routesDisposed = false;
  const disposeRoutes = () => {
    if (routesDisposed) return;
    routesDisposed = true;
    for (const dispose of disposers.splice(0).reverse()) {
      try {
        dispose();
      } catch (error) {
        warn(`dsh-vocab-app 注销路由失败：${error && error.message ? error.message : error}`);
      }
    }
  };
  const registerRoute = (route) => {
    const dispose = connection.fetch.register(route);
    if (typeof dispose === 'function') disposers.push(dispose);
    return dispose;
  };

  try {
    ctx.effect(() => {
      try {
        registerRoute({
          path: STATE_PATH,
          methods: ['GET'],
          requestBody: 'buffered',
          fetch: handlers.state,
        });
        registerRoute({
          path: ACTION_PATH,
          methods: ['POST'],
          requestBody: 'buffered',
          fetch: handlers.action,
        });
      } catch (error) {
        // 部分注册失败：先注销已注册路由（逐个独立，避免二次异常掩盖原错误），
        // 再释放 engine（已同步取到的锁），最后把注册错误抛给宿主。
        disposeRoutes();
        closeEngineQuietly(engine);
        throw error;
      }
      return () => {
        try {
          disposeRoutes();
        } finally {
          // 无论 disposer 是否抛错，都必须释放记录锁；engine.close 幂等。
          closeEngineQuietly(engine);
        }
      };
    }, 'dsh-vocab-app: /api/vocab-app state+action routes');
  } catch (error) {
    // ctx.effect 自身失败（可能在 factory 已成功返回 cleanup 之后）：仍要清掉
    // 已注册路由并关闭引擎，避免“路由已挂载但无人注销 + 锁泄漏”。
    disposeRoutes();
    closeEngineQuietly(engine);
    throw error;
  }

  return engine;
}

export default { name, inject, apply };
