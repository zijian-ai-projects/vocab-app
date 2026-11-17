/** Isolated CPU work: receives only the public dictionary, never learning records. */
import { parentPort, workerData } from 'node:worker_threads';
import { FrequencyBank } from '../core/vocabulary_test.js';

if (!parentPort) throw new Error('Quiz-bank worker requires a parent port');
try {
  const bank = new FrequencyBank(workerData.words, (percent) => {
    parentPort.postMessage({ type: 'progress', percent });
  });
  parentPort.postMessage({ type: 'ready', bank });
} catch (error) {
  parentPort.postMessage({ type: 'failed', message: String(error && error.message || error) });
} finally {
  parentPort.close();
}
