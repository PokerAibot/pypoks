"""

 2019 (c) piteren

"""

import tensorflow as tf

from pUtils.littleTools.littleMethods import shortSCIN
from pUtils.nnTools.nnBaseElements import defInitializer, layDENSE, numVFloats, gradClipper, lRscaler
from pUtils.nnTools.nnEncoders import encDR, encTRNS
from pUtils.nnTools.dvc.dvcModel import DVCmodel
from pUtils.nnTools.dvc.dvcPresets import dvcPresets, setFulldvcDict

# base LSTM neural graph
def lstmGraphFN(
        scope :str,
        wC=         16,     # card (single) emb width
        wMT=        1,      # move type emb width
        wV=         11,     # values vector width, holds player move data(type, pos, cash)
        nDR=        3,      # num of encDR lay
        cellW=      1024,   # cell width
        optAda=     True,
        lR=         7e-6):

    with tf.variable_scope(scope):

        print()
        inC = tf.placeholder(  # 7 cards
            name=           'inC',
            dtype=          tf.int32,
            shape=          [None, None, 7])  # [bsz,seq,7cards]

        cEMB = tf.get_variable(  # cards embeddings
            name=           'cEMB',
            shape=          [53, wC],  # one card for 'no_card'
            dtype=          tf.float32,
            initializer=    defInitializer())

        inCemb = tf.nn.embedding_lookup(params=cEMB, ids=inC)
        print(' > inCemb:', inCemb)
        inCemb = tf.unstack(inCemb, axis=-2)
        inCemb = tf.concat(inCemb, axis=-1)
        print(' > inCemb (flattened):', inCemb)

        inMT = tf.placeholder(  # event type
            name=           'inMT',
            dtype=          tf.int32,
            shape=          [None, None, 4])  # [bsz,seq,2*2oppon]

        mtEMB = tf.get_variable(  # event type embeddings
            name=           'mtEMB',
            shape=          [5, wMT],  # 4 moves + no_move
            dtype=          tf.float32,
            initializer=    defInitializer())

        inMTemb = tf.nn.embedding_lookup(params=mtEMB, ids=inMT)
        print(' > inMTemb:', inMTemb)
        inMTemb = tf.unstack(inMTemb, axis=-2)
        inMTemb = tf.concat(inMTemb, axis=-1)
        print(' > inMTemb (flattened):', inMTemb)

        inV = tf.placeholder(  # event float values
            name=           'inV',
            dtype=          tf.float32,
            shape=          [None, None, 4, wV])  # [bsz,seq,2*2,vec]

        inVec = tf.unstack(inV, axis=-2)
        inVec = tf.concat(inVec, axis=-1)
        print(' > inV (flattened):', inVec)

        input = tf.concat([inCemb, inMTemb, inVec], axis=-1)
        print(' > input (concatenated):', input)  # width = self.wC*3 + (self.wMT + self.wV)*2

        encDRout = encDR(
            input=      input,
            nLayers=    nDR,
            layWidth=   cellW,
            nHL=        0,
            verbLev=    1)
        input = encDRout['output']

        inState = tf.placeholder(
            name=           'state',
            dtype=          tf.float32,
            shape=          [None, 2, cellW])

        singleZeroState = tf.zeros(shape=[2, cellW])

        # state is a tensor of shape [batch_size, cell_state_size]
        c, h = tf.unstack(inState, axis=1)
        cellZS = tf.nn.rnn_cell.LSTMStateTuple(c, h)
        print(' > cell zero state:', cellZS)

        cell = tf.contrib.rnn.NASCell(cellW)
        out, state = tf.nn.dynamic_rnn(
            cell=           cell,
            inputs=         input,
            initial_state=  cellZS,
            dtype=          tf.float32)

        print(' > out:', out)
        print(' > state:', state)
        state = tf.concat(state, axis=-1)
        finState = tf.reshape(state, shape=[-1, 2, cellW])
        print(' > finState:', finState)

        denseOut = layDENSE(
            input=      out,
            units=      4,
            #activation= tf.nn.relu,
            useBias=    False,)
        logits = denseOut['output']
        print(' > logits:', logits)

        probs = tf.nn.softmax(logits)

        vars = tf.trainable_variables(scope=tf.get_variable_scope().name)
        print(' ### num of vars %s' % shortSCIN(numVFloats(vars)))

        move = tf.placeholder(  # "correct" move (class)
            name=           'move',
            dtype=          tf.int32,
            shape=          [None, None])  # [bsz,seq]

        reward = tf.placeholder(  # reward for "correct" move
            name=           'reward',
            dtype=          tf.float32,
            shape=          [None, None])  # [bsz,seq]

        rew = reward/500 # lineary scale rewards

        # this loss is auto averaged with reduction parameter
        #loss = tf.losses.SparseCategoricalCrossentropy(from_logits=True)
        #loss = loss(y_true=move, y_pred=logits, sample_weight=rew)
        loss = tf.losses.sparse_softmax_cross_entropy(
            labels=     move,
            logits=     logits,
            weights=    rew)

        gradients = tf.gradients(loss, vars)
        gN = tf.global_norm(gradients)

        gradients, _ = tf.clip_by_global_norm(t_list=gradients, clip_norm=1, use_norm=gN)

        optimizer = tf.train.AdamOptimizer(lR) if optAda else tf.train.GradientDescentOptimizer(lR)
        optimizer = optimizer.apply_gradients(zip(gradients, vars))

        # select optimizer vars
        optVars = []
        for var in tf.global_variables(scope=tf.get_variable_scope().name):
            if var not in vars: optVars.append(var)

        return{
            'scope':                scope,
            'inC':                  inC,
            'inMT':                 inMT,
            'inV':                  inV,
            'wV':                   wV,
            'move':                 move,
            'reward':               reward,
            'inState':              inState,
            'singleZeroState':      singleZeroState,
            'probs':                probs,
            'finState':             finState,
            'optimizer':            optimizer,
            'loss':                 loss,
            'gN':                   gN,
            'vars':                 vars,
            'optVars':              optVars}

# base CNN+RES neural graph
def cnnRGraphFN(
        scope :str,
        wC=         16,     # card (single) emb width
        wMT=        1,      # move type emb width
        wV=         11,     # values vector width, holds player move data(type, pos, cash)
        nLay=       24,     # number of CNNR layers
        reW=        512,    # representation width (number of filters)
        optAda=     True,
        lR=         7e-7):

    with tf.variable_scope(scope):

        print()
        inC = tf.placeholder(  # 7 cards
            name=           'inC',
            dtype=          tf.int32,
            shape=          [None, None, 7])  # [bsz,seq,7cards]

        cEMB = tf.get_variable(  # cards embeddings
            name=           'cEMB',
            shape=          [53, wC],  # one card for 'no_card'
            dtype=          tf.float32,
            initializer=    defInitializer())

        inCemb = tf.nn.embedding_lookup(params=cEMB, ids=inC)
        print(' > inCemb:', inCemb)
        inCemb = tf.unstack(inCemb, axis=-2)
        inCemb = tf.concat(inCemb, axis=-1)
        print(' > inCemb (flattened):', inCemb)

        inMT = tf.placeholder(  # event type
            name=           'inMT',
            dtype=          tf.int32,
            shape=          [None, None, 4])  # [bsz,seq,2*2oppon]

        mtEMB = tf.get_variable(  # event type embeddings
            name=           'mtEMB',
            shape=          [5, wMT],  # 4 moves + no_move
            dtype=          tf.float32,
            initializer=    defInitializer())

        inMTemb = tf.nn.embedding_lookup(params=mtEMB, ids=inMT)
        print(' > inMTemb:', inMTemb)
        inMTemb = tf.unstack(inMTemb, axis=-2)
        inMTemb = tf.concat(inMTemb, axis=-1)
        print(' > inMTemb (flattened):', inMTemb)

        inV = tf.placeholder(  # event float values
            name=           'inV',
            dtype=          tf.float32,
            shape=          [None, None, 4, wV])  # [bsz,seq,2*2,vec]

        inVec = tf.unstack(inV, axis=-2)
        inVec = tf.concat(inVec, axis=-1)
        print(' > inV (flattened):', inVec)

        input = tf.concat([inCemb, inMTemb, inVec], axis=-1)
        print(' > input (concatenated):', input)  # width = self.wC*3 + (self.wMT + self.wV)*2

        # projection without activation and bias
        denseOut = layDENSE(
            input=          input,
            units=          reW,
            useBias=        False,
            initializer=    defInitializer())
        projInput = denseOut['output']
        print(' > projInput (projected):', projInput)

        inState = tf.placeholder(
            name=           'state',
            dtype=          tf.float32,
            shape=          [None,nLay,2,reW]) # [bsz,nLay,2,reW]

        singleZeroState = tf.zeros(shape=[nLay,2,reW]) # [nLay,2,reW]

        # unstack layers of inState
        inStateLays = tf.unstack(inState, axis=-3)
        print(' > inStateLays len %d of:' %len(inStateLays), inStateLays[0])

        subOutput = tf.contrib.layers.layer_norm(
            inputs=             projInput,
            begin_norm_axis=    -1,
            begin_params_axis=  -1)
        layInputLays = []
        for depth in range(nLay):

            layInputLays.append(tf.concat([inStateLays[depth],subOutput], axis=-2))
            print(' > layInput of %d lay'%depth, layInputLays[-1])

            layName = 'cnnREncLay_%d' % depth
            with tf.variable_scope(layName):

                convLay = tf.layers.Conv1D(
                    filters=            reW,
                    kernel_size=        3,
                    dilation_rate=      1,
                    activation=         None,
                    use_bias=           True,
                    kernel_initializer= defInitializer(),
                    padding=            'valid',
                    data_format=        'channels_last')

            cnnOutput = convLay(layInputLays[-1])
            cnnOutput = tf.nn.relu(cnnOutput) # activation
            print(' > cnnOutput of %d lay' % depth, cnnOutput)
            subOutput += cnnOutput
            print(' > subOutput (RES) of %d lay' % depth, cnnOutput)
            subOutput = tf.contrib.layers.layer_norm(
                inputs=             subOutput,
                begin_norm_axis=    -1,
                begin_params_axis=  -1)

        out = subOutput
        print(' > out:', out)

        state = tf.stack(layInputLays, axis=-3)
        print(' > state (stacked):', state)
        finState = tf.split(state, num_or_size_splits=[-1,2], axis=-2)[1]
        print(' > finState (split):', finState)


        # projection to logits
        denseOut = layDENSE(
            input=          out,
            units=          4,
            useBias=        False,
            initializer=    defInitializer())
        logits = denseOut['output']
        print(' > logits:', logits)

        probs = tf.nn.softmax(logits)

        vars = tf.trainable_variables(scope=tf.get_variable_scope().name)
        print(' ### num of vars %s' % shortSCIN(numVFloats(vars)))

        move = tf.placeholder(  # "correct" move (class)
            name=           'move',
            dtype=          tf.int32,
            shape=          [None, None])  # [bsz,seq]

        reward = tf.placeholder(  # reward for "correct" move
            name=           'reward',
            dtype=          tf.float32,
            shape=          [None, None])  # [bsz,seq]

        rew = reward/500 # lineary scale rewards

        # this loss is auto averaged with reduction parameter
        #loss = tf.losses.SparseCategoricalCrossentropy(from_logits=True)
        #loss = loss(y_true=move, y_pred=logits, sample_weight=rew)
        loss = tf.losses.sparse_softmax_cross_entropy(
            labels=     move,
            logits=     logits,
            weights=    rew)

        gradients = tf.gradients(loss, vars)
        gN = tf.global_norm(gradients)

        #gradients, _ = tf.clip_by_global_norm(t_list=gradients, clip_norm=1, use_norm=gN)

        optimizer = tf.train.AdamOptimizer(lR) if optAda else tf.train.GradientDescentOptimizer(lR)
        optimizer = optimizer.apply_gradients(zip(gradients, vars))

        # select optimizer vars
        optVars = []
        for var in tf.global_variables(scope=tf.get_variable_scope().name):
            if var not in vars: optVars.append(var)

        return{
            'scope':                scope,
            'inC':                  inC,
            'inMT':                 inMT,
            'inV':                  inV,
            'wV':                   wV,
            'move':                 move,
            'reward':               reward,
            'inState':              inState,
            'singleZeroState':      singleZeroState,
            'probs':                probs,
            'finState':             finState,
            'optimizer':            optimizer,
            'loss':                 loss,
            'gN':                   gN,
            'vars':                 vars,
            'optVars':              optVars}

# cards net graph
def cardGFN(
        scope=      'cardNG',
        cEmbW=      16,
        nLayers=    6,
        rWidth=     30,
        drLayers=   3, # None or 0
        lR=         1e-3,
        warmUp=     10000,
        annbLr=     0.999,
        stepLr=     0.1,
        doClip=     True):

    # DR encoder graph (cards representations)
    def cEncDR(
            sevenC,                     # seven cards placeholder
            cEMB,                       # cards embedding tensor
            scope=      'cEncDR',
            nLayers=    6,
            rWidth=     30):            # width of representation tensor

        inCemb = tf.nn.embedding_lookup(params=cEMB, ids=sevenC)
        print(' > inCemb:', inCemb)
        inCemb = tf.unstack(inCemb, axis=-2)
        inCemb = tf.concat(inCemb, axis=-1)
        print(' > inCemb (flattened):', inCemb)

        encOUT = encDR(
            input=      inCemb,
            name=       scope,
            nLayers=    nLayers,
            layWidth=   rWidth,
            nHL=        2,
            verbLev=    2)

        return {
            'output':   encOUT['output'],
            'histSumm': encOUT['histSumm'],
            'nnZeros':  encOUT['nnZeros']}

    # Transformer encoder graph (cards representations)
    def cEncT(
            sevenC,                     # seven cards placeholder
            cEMB,                       # cards embedding tensor
            nLayers=    6):

        print('\nBuilding cEncT (T encoder)...')

        inCemb = tf.nn.embedding_lookup(params=cEMB, ids=sevenC)
        print(' > inCemb:', inCemb)

        #""""
        myCEMB = tf.get_variable(  # my cards embeddings
            name=           'myCEMB',
            shape=          [2, cEMB.shape[-1]],
            dtype=          tf.float32,
            initializer=    defInitializer())
        myCElook = tf.nn.embedding_lookup(params=myCEMB, ids=[0,0,1,1,1,1,1])
        print(' > myCElook:', myCElook)
        inCemb += myCElook
        #"""
        cProjOUT = layDENSE(
            input=          inCemb,
            units=          48,
            name=           'cProj',
            reuse=          tf.AUTO_REUSE,
            useBias=        False,
            initializer=    defInitializer())
        #inCemb = cProjOUT['output']
        print(' > inCemb projected:', inCemb)
        #"""

        TATcase = True # hardcoded TAT, which performs well
        encOUT = encTRNS(
            input=      inCemb,
            seqOut=     not TATcase,
            addPE=      False,
            name=       'cTrans',
            nBlocks=    nLayers,
            nHeads=     1,
            denseMul=   24,#4,
            maxSeqLen=  7,
            nHistL=     2,
            verbLev=    2)

        output = encOUT['eTOut']
        if not TATcase:
            output = tf.unstack(output, axis=-2)
            output = tf.concat(output, axis=-1)
        print(' > encT reshaped output:', output)

        return {
            'output':   output,
            'histSumm': encOUT['histSumm'],
            'nnZeros':  encOUT['nnZeros']}

    with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):

        cEMB = tf.get_variable(  # cards embeddings
            name=           'cEMB',
            shape=          [53, cEmbW],  # one card for 'no_card'
            dtype=          tf.float32,
            initializer=    defInitializer())

        histSumm = [tf.summary.histogram('cEMB', cEMB, family='cEMB')]

        inAC = tf.placeholder(  # 7 cards of A
            name=           'inAC',
            dtype=          tf.int32,
            shape=          [None, 7])  # [bsz,7cards]

        inBC = tf.placeholder(  # 7 cards of B
            name=           'inBC',
            dtype=          tf.int32,
            shape=          [None, 7])  # [bsz,7cards]

        won = tf.placeholder(  # won class
            name=           'won',
            dtype=          tf.int32,
            shape=          [None])  # [bsz,seq]

        rnkA = tf.placeholder( # rank A class
            name=           'rnkA',
            dtype=          tf.int32,
            shape=          [None])  # [bsz,seq]

        rnkB = tf.placeholder( # rank B class
            name=           'rnkB',
            dtype=          tf.int32,
            shape=          [None])  # [bsz,seq]

        #cRGAout = cEncDR(inAC, cEMB, nLayers=nLayers, rWidth=rWidth)
        #cRGBout = cEncDR(inBC, cEMB, nLayers=nLayers, rWidth=rWidth)
        cRGAout = cEncT(inAC, cEMB, nLayers=nLayers)
        cRGBout = cEncT(inBC, cEMB, nLayers=nLayers)
        nnZeros = cRGAout['nnZeros']
        nnZeros = tf.reshape(tf.stack(nnZeros), shape=[-1])

        denseOutA = layDENSE(
            input=          cRGAout['output'],
            units=          9,
            name=           'denseRC',
            useBias=        False,
            initializer=    defInitializer())
        rankAlogits = denseOutA['output']

        denseOutB = layDENSE(
            input=          cRGBout['output'],
            units=          9,
            name=           'denseRC',
            reuse=          True,
            useBias=        False,
            initializer=    defInitializer())
        rankBlogits = denseOutB['output']

        output = tf.concat([cRGAout['output'],cRGBout['output']], axis=-1)
        print('\n > concRepr:', output)

        histSumm.append(cRGAout['histSumm'])

        # dense classifier
        if drLayers:
            encOUT = encDR(
                input=      output,
                name=       'drC',
                nLayers=    drLayers,
                layWidth=   rWidth*2,
                nHL=        0,
                verbLev=    2)
            output = encOUT['output']

        # projection to logits
        denseOut = layDENSE(
            input=          output,
            units=          3,
            useBias=        False,
            initializer=    defInitializer())
        wonLogits = denseOut['output']
        print(' > logits:', wonLogits)

        vars = tf.trainable_variables()
        print(' ### num of (%d) vars %s'%(len(vars), shortSCIN(numVFloats(vars))))
        #for var in vars: print(var)

        lossRA = tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels= rnkA,
            logits= rankAlogits)
        lossRA = tf.reduce_mean(lossRA)

        lossRB = tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels= rnkB,
            logits= rankBlogits)
        lossRB = tf.reduce_mean(lossRB)
        lossR = lossRA+lossRB
        print(' > lossR:', lossR)

        lossW = tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels=     won,
            logits=     wonLogits)
        lossW = tf.reduce_mean(lossW)
        print(' > lossW:', lossW)
        loss = lossW+lossR

        predictionsRA = tf.argmax(rankAlogits, axis=-1, output_type=tf.int32)
        predictionsRB = tf.argmax(rankBlogits, axis=-1, output_type=tf.int32)
        correctRA = tf.equal(predictionsRA, rnkA)
        correctRB = tf.equal(predictionsRB, rnkB)
        avgAccR = tf.reduce_mean(tf.cast(correctRA, dtype=tf.float32)) + tf.reduce_mean(tf.cast(correctRB, dtype=tf.float32))
        avgAccR /= 2
        print(' > avgAccR:', avgAccR)

        ohRnkA = tf.one_hot(indices=rnkA, depth=9)
        ohRnkB = tf.one_hot(indices=rnkB, depth=9)
        rnkAdensity = tf.reduce_mean(ohRnkA, axis=-2)
        rnkBdensity = tf.reduce_mean(ohRnkB, axis=-2)
        ohCorrectRA = tf.where(condition=correctRA, x=ohRnkA, y=tf.zeros_like(ohRnkA))
        ohCorrectRB = tf.where(condition=correctRB, x=ohRnkB, y=tf.zeros_like(ohRnkB))
        rnkAcorrDensity = tf.reduce_mean(ohCorrectRA, axis=-2)
        rnkBcorrDensity = tf.reduce_mean(ohCorrectRB, axis=-2)
        avgAccRC = (rnkAcorrDensity/rnkAdensity + rnkBcorrDensity/rnkBdensity)/2

        ohNotCorrectRA = tf.where(condition=tf.logical_not(correctRA), x=ohRnkA, y=tf.zeros_like(ohRnkA))

        predictions = tf.argmax(wonLogits, axis=-1, output_type=tf.int32)
        print(' > predictions:', predictions)
        correct = tf.equal(predictions, won)
        print(' > correct:', correct)
        avgAcc = tf.reduce_mean(tf.cast(correct, dtype=tf.float32))
        print(' > avgAcc:', avgAcc)

        ohWon = tf.one_hot(indices=won, depth=3)
        wonDensity = tf.reduce_mean(ohWon, axis=-2)
        ohCorrect = tf.where(condition=correct, x=ohWon, y=tf.zeros_like(ohWon))
        wonCorrDensity = tf.reduce_mean(ohCorrect, axis=-2)
        avgAccC = wonCorrDensity / wonDensity

        ohNotCorrect = tf.where(condition=tf.logical_not(correct), x=ohWon, y=tf.zeros_like(ohWon))

        globalStep = tf.get_variable(  # global step
            name=           'gStep',
            shape=          [],
            trainable=      False,
            initializer=    tf.constant_initializer(0),
            dtype=          tf.int32)

        lRs = lRscaler(
            iLR=            lR,
            gStep=          globalStep,
            warmUpSteps=    warmUp,
            annbLr=         annbLr,
            stepLr=         stepLr,
            verbLev=        1)

        optimizer = tf.train.AdamOptimizer(lRs)

        gradients = tf.gradients(loss, vars)
        clipOUT = gradClipper(gradients, doClip=doClip)
        gradients = clipOUT['gradients']
        gN = clipOUT['gGNorm']
        agN = clipOUT['avtGGNorm']
        optimizer = optimizer.apply_gradients(zip(gradients, vars), global_step=globalStep)

        # select optimizer vars
        optVars = []
        for var in tf.global_variables(scope=tf.get_variable_scope().name):
            if var not in vars: optVars.append(var)

        return{
            'scope':                scope,
            'inAC':                 inAC,
            'inBC':                 inBC,
            'won':                  won,
            'rnkA':                 rnkA,
            'rnkB':                 rnkB,
            'loss':                 loss,
            'acc':                  avgAcc,
            'accC':                 avgAccC,
            'predictions':          predictions,
            'ohNotCorrect':         ohNotCorrect,
            'accR':                 avgAccR,
            'accRC':                avgAccRC,
            'predictionsRA':        predictionsRA,
            'ohNotCorrectRA':       ohNotCorrectRA,
            'lRs':                  lRs,
            'gN':                   gN,
            'agN':                  agN,
            'vars':                 vars,
            'optVars':              optVars,
            'optimizer':            optimizer,
            'histSumm':             tf.summary.merge(histSumm),
            'nnZeros':              nnZeros}
